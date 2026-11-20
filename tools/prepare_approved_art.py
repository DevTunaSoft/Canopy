#!/usr/bin/env python3
"""Install unchanged, hash-verified Canopy Classic artwork from the actual selections.

No image processing, conversion, cropping, resizing, or invented replacements.
Runs only when the exact user-approved source files are provided locally.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "prototype/classic/assets/approved/manifest.json"


class ArtworkError(ValueError):
    pass


def read_manifest(path: Path = MANIFEST) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    icons = manifest.get("icons", [])
    if manifest.get("schema_version") != 1 or len(icons) != 8:
        raise ArtworkError("Expected schema v1 and exactly eight icon masters")
    names = [item.get("name") for item in icons]
    if names != ["Browser", "Mail", "Files", "Calendar", "Photos",
                 "Music", "Terminal", "Settings"]:
        raise ArtworkError("Icon names/order do not match approved selection")
    records = icons + [manifest["wallpaper"]]
    paths = [item.get("path") for item in records]
    if len(set(paths)) != 9:
        raise ArtworkError("Asset paths must be unique")
    for entry in records:
        path = entry.get("path", "")
        if (not isinstance(path, str) or not path.endswith(".png") or
                Path(path).is_absolute() or ".." in Path(path).parts or
                path.startswith("/") or "\\" in path or
                not isinstance(entry.get("sha256"), str) or
                len(entry["sha256"]) != 64):
            raise ArtworkError("Invalid approved asset path or SHA-256")
    return manifest


def check_exact(path: Path, expected: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise ArtworkError(f"Approved source is missing or a symlink: {path}")
    if path.stat().st_size > 12_000_000:
        raise ArtworkError("Asset exceeds the safe source size limit")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ArtworkError(
            f"Artwork SHA-256 mismatch for {path.name}: no substitutions allowed")


def prepare(icons_dir: Path, wallpaper: Path, destination: Path,
            manifest_path: Path = MANIFEST) -> None:
    manifest = read_manifest(manifest_path)
    inputs = {
        entry["path"]: icons_dir / Path(entry["path"]).name
        for entry in manifest["icons"]
    }
    inputs[manifest["wallpaper"]["path"]] = wallpaper
    entries = manifest["icons"] + [manifest["wallpaper"]]
    # Complete input verification BEFORE writing a single byte.
    for entry in entries:
        check_exact(inputs[entry["path"]], entry["sha256"])

    if destination.exists():
        if not destination.is_dir() or destination.is_symlink():
            raise ArtworkError("Destination exists but is not a safe directory")
        for entry in entries:
            check_exact(destination / entry["path"], entry["sha256"])
        return  # Idempotent, verified install; no copy or overwrite.

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".canopy-art-staging-", dir=destination.parent
    ) as staging:
        stage = Path(staging) / "approved-art"
        stage.mkdir()
        for entry in entries:
            target = stage / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inputs[entry["path"]], target)
            check_exact(target, entry["sha256"])
        # The final directory appears all at once. Never mix partial icon sets.
        stage.rename(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icons-dir", type=Path, required=True,
                        help="Directory containing all eight exact approved PNG crops")
    parser.add_argument("--wallpaper", type=Path, required=True,
                        help="Previously selected blue wave PNG (not a generated substitute)")
    parser.add_argument("--destination", type=Path, required=True,
                        help="Empty output directory; verified existing output is a no-op")
    args = parser.parse_args()
    try:
        prepare(args.icons_dir, args.wallpaper, args.destination)
    except (OSError, KeyError, json.JSONDecodeError, ArtworkError) as exc:
        parser.exit(1, f"APPROVED_ASSET_INSTALL_FAILED: {exc}\n")
    print(f"APPROVED_ASSET_INSTALL_PASS: exact source bytes at {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
