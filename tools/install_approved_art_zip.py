#!/usr/bin/env python3
"""Safely stage exact Canopy Classic PNGs from the user-supplied ZIP archive.

The archive is an external input; no files are extracted via ZipFile.extractall.
Only the nine SHA-locked source PNGs are installed. This tool never changes
their bytes, generates substitute icons, or claims visual approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import tempfile
from zipfile import BadZipFile, ZipFile

from tools.prepare_approved_art import (
    ArtworkError, MANIFEST, check_exact, read_manifest,
)

MAX_ARCHIVE_BYTES = 30_000_000
MAX_ASSET_BYTES = 12_000_000
MAX_ARCHIVED_TEXT_BYTES = 65_536
MAX_TOTAL_BYTES = 110_000_000
MAX_MEMBERS = 20
ARCHIVE_PREFIX = "approved-art/"


def _hash_member(archive: ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(name) as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_archive(archive_path: Path, destination: Path,
                    manifest_path: Path = MANIFEST) -> None:
    """Validate all members, then atomically publish an immutable asset set."""
    manifest = read_manifest(manifest_path)
    entries = [*manifest["icons"], manifest["wallpaper"]]
    expected = {
        ARCHIVE_PREFIX + item["path"]: item["sha256"] for item in entries
    }
    allowed_directories = {
        "approved-art/", "approved-art/icons/", "approved-art/wallpaper/"
    }
    allowed_text = {"approved-art/manifest.json", "HOW_TO_USE.txt"}
    allowed = set(expected) | allowed_directories | allowed_text

    if (not archive_path.is_file() or archive_path.is_symlink() or
            archive_path.stat().st_size > MAX_ARCHIVE_BYTES):
        raise ArtworkError("ZIP is missing, a symlink, or too large")

    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_MEMBERS:
            raise ArtworkError("ZIP member count is outside the allowed range")
        seen = set()
        total_bytes = 0
        for item in infos:
            name = item.filename
            mode = (item.external_attr >> 16) & 0xFFFF
            if name in seen or name not in allowed:
                raise ArtworkError("Duplicate or unexpected ZIP path: " + name)
            seen.add(name)
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                raise ArtworkError("ZIP symlink entries are forbidden")
            if item.is_dir() != (name in allowed_directories):
                raise ArtworkError("Invalid ZIP member type: " + name)
            limit = (MAX_ASSET_BYTES if name in expected
                     else MAX_ARCHIVED_TEXT_BYTES)
            if item.file_size > limit or item.file_size < 0:
                raise ArtworkError("ZIP member exceeds safe size: " + name)
            if (item.file_size > 0 and
                    (item.compress_size == 0 or
                     item.file_size > item.compress_size * 200)):
                raise ArtworkError("ZIP member compression ratio unsafe")
            total_bytes += item.file_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise ArtworkError("ZIP expanded size exceeds safety limit")

        if not set(expected).issubset(seen):
            raise ArtworkError("ZIP is missing one or more exact PNG masters")
        if "approved-art/manifest.json" not in seen:
            raise ArtworkError("ZIP is missing its provenance manifest")
        packaged_manifest = json.loads(archive.read("approved-art/manifest.json"))
        if packaged_manifest != manifest:
            raise ArtworkError("ZIP provenance manifest differs from repository lock")

        # Digest the complete archive set before creating a destination.
        for name, sha256 in expected.items():
            if _hash_member(archive, name) != sha256:
                raise ArtworkError("Artwork SHA-256 mismatch: no substitutions allowed")

        if destination.is_symlink():
            raise ArtworkError("Destination symlink is not allowed")
        if destination.exists():
            if not destination.is_dir():
                raise ArtworkError("Destination exists but is not a directory")
            for entry in entries:
                check_exact(destination / entry["path"], entry["sha256"])
            return  # Verified existing installation; never overwrite.

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
                prefix=".canopy-art-staging-", dir=destination.parent) as temp:
            staged = Path(temp) / "approved-art"
            staged.mkdir()
            for entry in entries:
                source_name = ARCHIVE_PREFIX + entry["path"]
                target = staged / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(source_name) as source, target.open("wb") as out:
                    for chunk in iter(lambda: source.read(64 * 1024), b""):
                        out.write(chunk)
                check_exact(target, entry["sha256"])
            staged.rename(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True,
                        help="Original Canopy_Classic_Exact_Artwork_Runtime.zip")
    parser.add_argument("--destination", type=Path, required=True,
                        help="Approved-art directory to create (verified existing is a no-op)")
    args = parser.parse_args()
    try:
        install_archive(args.archive, args.destination)
    except (OSError, ValueError, KeyError, RuntimeError, BadZipFile,
            NotImplementedError, json.JSONDecodeError) as exc:
        parser.exit(1, f"APPROVED_ASSET_ZIP_FAILED: {exc}\n")
    print(f"APPROVED_ASSET_ZIP_PASS: nine exact SHA-locked PNGs at {args.destination}")
    print("This verifies source bytes only; Linux Mint and visual approval remain pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
