"""Pure, fail-closed helpers shared by the native baseline build and smoke tools.

No helper mutates a repository, a VM or a user session. Every SHA in this module
is a content identity pin, not an approval or release claim.
"""

from __future__ import annotations

import hashlib
import io
import re
import tarfile
from pathlib import Path

# Git commit pin: native Plasma integration base for this development baseline.
SOURCE_COMMIT = "ec910d7a7275296ecbc8b5e5c459d356205165d1"
# Approved wallpaper blob, byte-for-byte (SHA-256 of the PNG bytes).
APPROVED_WALLPAPER_SHA256 = "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381"
LEGACY_WALLPAPER_SHA256 = "1efa6e83deee160ce9cf225db010025f4f162975f4dfc23e6da3f3ca0973528a"
PACKAGE_ID = "org.kde.plasma.canopyclassic"
PACKAGE_VERSION = "0.1.0-dev-baseline"
WALLPAPER_NAME = "Canopy_Classic_Master_Wallpaper_1920x1080.png"
HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def is_hex40(value: object) -> bool:
    return isinstance(value, str) and bool(HEX40.fullmatch(value))


def is_hex64(value: object) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def canonical_sha256(value: object) -> str | None:
    """Lowercase canonical SHA-256 or None for malformed input (fail closed)."""
    return value.lower() if is_hex64(value) else None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def path_string(path: Path) -> str:
    """Native forward-slash path (the tooling runs on Windows hosts too)."""
    return str(path).replace("\\", "/")


def _tar_info(name: str, data: bytes, executable: bool) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if executable else 0o644
    info.type = tarfile.REGTYPE
    return info


def _dir_info(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name.rstrip("/") + "/")
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755
    info.type = tarfile.DIRTYPE
    info.size = 0
    return info


def collect_files(root: Path) -> list[tuple[str, Path]]:
    """Deterministic, symlink-free relative-path inventory of a staged tree."""
    root = Path(root)
    entries: list[tuple[str, Path]] = []
    for current, dirs, files in __import__("os").walk(root, followlinks=False):
        dirs.sort()
        current_path = Path(current)
        for name in sorted(dirs):
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError("symlink in staged tree: %s" % path_string(candidate))
        for name in sorted(files):
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError("symlink in staged tree: %s" % path_string(candidate))
            entries.append((candidate.relative_to(root).as_posix(), candidate))
    entries.sort(key=lambda pair: pair[0])
    return entries


def write_deterministic_tarball(root: Path, destination: Path) -> str:
    """Create a byte-stable tar.gz and return its SHA-256.

    Members are sorted POSIX paths with mtime=0, uid/gid=0, empty uname/gname and
    GNU tar format. Gzip carries no filename and mtime=0. No wall-clock value
    enters the archive bytes.
    """
    root = Path(root)
    destination = Path(destination)
    entries = collect_files(root)
    seen_dirs: set[str] = set()
    for relative, _ in entries:
        parts = relative.split("/")
        for depth in range(1, len(parts)):
            seen_dirs.add("/".join(parts[:depth]))

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for directory in sorted(seen_dirs):
            archive.addfile(_dir_info(directory))
        for relative, source in entries:
            data = source.read_bytes()
            executable = bool(source.stat().st_mode & 0o111)
            archive.addfile(_tar_info(relative, data, executable), io.BytesIO(data))
    payload = raw.getvalue()

    destination.parent.mkdir(parents=True, exist_ok=True)
    import gzip

    with open(destination, "wb") as stream:
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9,
                           mtime=0, fileobj=stream) as zipped:
            zipped.write(payload)
    return sha256_file(destination)


def make_sha256sums(root: Path, skip: frozenset[str] = frozenset()) -> str:
    """GNU-style SHA256SUMS text over a staged tree, sorted by relative path."""
    lines = []
    for relative, source in collect_files(root):
        if relative in skip:
            continue
        lines.append("%s  %s" % (sha256_file(source), relative))
    return "\n".join(lines) + "\n" if lines else ""


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse SHA256SUMS lines; reject duplicate paths and malformed hashes."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" ") and len(line) >= 66 and line[64] in " \t":
            digest, name = line[:64], line[66:]
            binary = line[65] == "*"
        elif line.startswith(" ") and len(line) >= 67 and line[65] in " \t":
            digest, name = line[1:65], line[67:]
            binary = line[66] == "*"
        else:
            raise ValueError("malformed SHA256SUMS line")
        canonical = canonical_sha256(digest)
        if canonical is None or not name or name in result or binary:
            raise ValueError("invalid or duplicate SHA256SUMS entry: %r" % name)
        result[name] = canonical
    return result


def check_manifest_pins(manifest: dict, approved_root: Path) -> dict[str, str]:
    """Verify the approved manifest and return name -> sha256 for its icons."""
    if not isinstance(manifest, dict):
        raise ValueError("approved manifest is not an object")
    icons = manifest.get("icons")
    if not isinstance(icons, list) or len(icons) != 8:
        raise ValueError("approved manifest must pin exactly eight icons")
    pins: dict[str, str] = {}
    for item in icons:
        if not isinstance(item, dict):
            raise ValueError("icon entry is not an object")
        name, relative, digest = item.get("name"), item.get("path"), item.get("sha256")
        if not isinstance(name, str) or not isinstance(relative, str):
            raise ValueError("icon name/path is not a string")
        canonical = canonical_sha256(digest)
        if canonical is None:
            raise ValueError("icon %s has an invalid SHA pin" % name)
        actual = approved_root / relative
        if not actual.is_file():
            raise ValueError("missing approved icon %s" % path_string(actual))
        if sha256_file(actual) != canonical:
            raise ValueError("approved icon hash mismatch: %s" % name)
        pins[relative] = canonical
    if len(set(pins.values())) != 8:
        raise ValueError("approved icon hashes are not distinct")
    return pins
