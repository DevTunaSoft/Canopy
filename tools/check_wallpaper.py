#!/usr/bin/env python3
"""Fail-closed gate for the exact approved Canopy Classic alpine wallpaper.

The only accepted default image is the owner-approved 1920x1080 PNG whose
SHA-256 is pinned below. The gate never generates, recompresses or substitutes
artwork; it recomputes every hash from bytes on disk and refuses symlinks,
wrong dimensions, extra substitute files, and a legacy blue-wave default.

Usage:
    python tools/check_wallpaper.py verify --root REPO [--json]
    python tools/check_wallpaper.py selftest
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import struct
import sys
import tempfile
from pathlib import Path

APPROVED_SHA256 = "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381"
APPROVED_BYTES = 3_107_170
APPROVED_SIZE = (1920, 1080)
MASTER_NAME = "Canopy_Classic_Master_Wallpaper_1920x1080.png"
APPROVED_ASSET = Path("prototype/classic/assets/approved/wallpaper") / MASTER_NAME
DUPLICATE_ASSET = Path("prototype/classic/assets/wallpapers") / MASTER_NAME
MAIN_QML = Path("prototype/classic/Main.qml")
WALLPAPER_QML = Path("prototype/classic/Wallpaper.qml")
HISTORICAL_FILES = {
    "canopy-wave-preview.png",
    "blue-current.svg",
    "INTEGRATION_EVIDENCE.md",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class WallpaperError(ValueError):
    """Stable, fail-closed gate error."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def png_dimensions(raw: bytes) -> tuple[int, int]:
    """Read IHDR dimensions without decoding or trusting image metadata."""
    if len(raw) < 33 or not raw.startswith(PNG_SIGNATURE):
        raise WallpaperError("not a PNG file")
    if raw[12:16] != b"IHDR" or struct.unpack(">I", raw[8:12])[0] != 13:
        raise WallpaperError("PNG IHDR missing or malformed")
    width, height, depth, color = struct.unpack(">IIBB", raw[16:26])
    if depth != 8 or color not in (0, 2, 6):
        raise WallpaperError("unsupported PNG bit depth or colour type")
    if width <= 0 or height <= 0 or width > 20000 or height > 20000:
        raise WallpaperError("implausible PNG dimensions")
    return width, height


def _asset(root: Path, relative: Path, expected_sha: str, expected_bytes: int,
           problems: list[str]) -> bytes | None:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        problems.append(f"missing or symlinked asset: {relative.as_posix()}")
        return None
    raw = path.read_bytes()
    if len(raw) != expected_bytes:
        problems.append(f"wrong size: {relative.as_posix()}={len(raw)}")
    if not hmac.compare_digest(sha256_bytes(raw), expected_sha):
        problems.append(f"SHA-256 mismatch: {relative.as_posix()}")
    try:
        dimensions = png_dimensions(raw)
    except WallpaperError as exc:
        problems.append(f"{relative.as_posix()}: {exc}")
    else:
        if dimensions != APPROVED_SIZE:
            problems.append(
                f"wrong dimensions: {relative.as_posix()}={dimensions[0]}x{dimensions[1]}")
    return raw


def check(root: Path, expected_sha: str = APPROVED_SHA256,
          expected_bytes: int = APPROVED_BYTES) -> dict:
    """Return a fail-closed report; never writes to *root*."""
    problems: list[str] = []
    root = Path(root)
    hashes: dict[str, str] = {}
    try:
        first = _asset(root, APPROVED_ASSET, expected_sha, expected_bytes, problems)
        second = _asset(root, DUPLICATE_ASSET, expected_sha, expected_bytes, problems)
        if first is not None:
            hashes[APPROVED_ASSET.as_posix()] = sha256_bytes(first)
        if second is not None:
            hashes[DUPLICATE_ASSET.as_posix()] = sha256_bytes(second)
        if first is not None and second is not None and not hmac.compare_digest(first, second):
            problems.append("asset copies differ")

        for directory in (APPROVED_ASSET.parent, DUPLICATE_ASSET.parent):
            folder = root / directory
            if folder.is_dir():
                for item in sorted(folder.iterdir()):
                    if item.name not in HISTORICAL_FILES and item.name != MASTER_NAME:
                        problems.append(f"unexpected wallpaper candidate: {directory.as_posix()}/{item.name}")

        main_path = root / MAIN_QML
        if not main_path.is_file():
            problems.append("Main.qml missing")
        else:
            main_text = main_path.read_text(encoding="utf-8", errors="replace")
            required = (
                "Wallpaper { anchors.fill: parent }",
                MASTER_NAME,
                "approvedMasterWallpaperUrl",
                "Qt.binding",
                "canopyLandscapeWallpaperUrl.length > 0",
                "child.objectName === \"canopyWallpaperImage\"",
            )
            for token in required:
                if token not in main_text:
                    problems.append(f"Main.qml missing default-selection token: {token}")
            for forbidden in ("blue-current.svg", "canopy-wave-preview.png"):
                if forbidden in main_text:
                    problems.append(f"Main.qml still selects legacy wallpaper: {forbidden}")

        wallpaper_path = root / WALLPAPER_QML
        if not wallpaper_path.is_file():
            problems.append("Wallpaper.qml missing")
        else:
            qml_text = wallpaper_path.read_text(encoding="utf-8", errors="replace")
            if "Image.PreserveAspectCrop" not in qml_text:
                problems.append("aspect-preserving fill mode missing")
            if qml_text.count("Image {") != 1:
                problems.append("wallpaper must decode exactly one runtime image")
    except (OSError, ValueError, struct.error) as exc:
        problems.append("gate error: " + type(exc).__name__ + ": " + str(exc)[:120])

    return {
        "status": "FAIL" if problems else "PASS",
        "expected_sha256": expected_sha,
        "expected_bytes": expected_bytes,
        "problems": problems,
        "hashes": hashes,
    }


def _write_fixture(root: Path, raw: bytes) -> None:
    for relative in (APPROVED_ASSET, DUPLICATE_ASSET, MAIN_QML, WALLPAPER_QML):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative in (APPROVED_ASSET, DUPLICATE_ASSET):
            path.write_bytes(raw)
        else:
            path.write_text(
                "Wallpaper { anchors.fill: parent }\n"
                "Canopy_Classic_Master_Wallpaper_1920x1080.png\n"
                "approvedMasterWallpaperUrl Qt.binding\n"
                "canopyLandscapeWallpaperUrl.length > 0\n"
                'child.objectName === "canopyWallpaperImage"\n'
                if relative == MAIN_QML else
                "Image {}\nImage.PreserveAspectCrop\n",
                encoding="utf-8")


def _fake_png(width: int = 1920, height: int = 1080) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr + struct.pack(">I", zlib_crc(b"IHDR" + ihdr))
    return PNG_SIGNATURE + struct.pack(">I", 13) + chunk + struct.pack(">I", 0)


def zlib_crc(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def selftest() -> int:
    """Prove the gate is green on a fixture and red on pinned negative controls."""
    with tempfile.TemporaryDirectory(prefix="canopy-wallpaper-gate-") as temp:
        root = Path(temp) / "green"
        raw = _fake_png()
        expected = sha256_bytes(raw)
        _write_fixture(root, raw)
        result = check(root, expected, len(raw))
        if result["status"] != "PASS":
            print("WALLPAPER_SELFTEST_FAIL: green fixture", result["problems"])
            return 1

        negatives = []
        bad = Path(temp) / "tampered"
        _write_fixture(bad, raw)
        (bad / APPROVED_ASSET).write_bytes(raw + b"\x00")
        negatives.append(("tampered_bytes", check(bad, expected, len(raw))))

        missing = Path(temp) / "missing"
        _write_fixture(missing, raw)
        (missing / DUPLICATE_ASSET).unlink()
        negatives.append(("missing_duplicate", check(missing, expected, len(raw))))

        wrong = Path(temp) / "wrong_dimensions"
        _write_fixture(wrong, _fake_png(1200, 750))
        negatives.append(("wrong_dimensions", check(wrong, sha256_bytes(_fake_png(1200, 750)), len(_fake_png(1200, 750)))))

        legacy = Path(temp) / "legacy"
        _write_fixture(legacy, raw)
        main_path = legacy / MAIN_QML
        main_path.write_text(main_path.read_text(encoding="utf-8") + "blue-current.svg\n",
                             encoding="utf-8")
        negatives.append(("legacy_selection", check(legacy, expected, len(raw))))

        for name, result in negatives:
            if result["status"] != "FAIL" or not result["problems"]:
                print("WALLPAPER_SELFTEST_FAIL: negative control not red:", name)
                return 1
            print(f"WALLPAPER_NEGATIVE {name} PASS detail={result['problems'][0][:80]}")
    print("WALLPAPER_SELFTEST PASS: green=1 negatives=4")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, default=Path.cwd())
    verify.add_argument("--json", action="store_true")
    sub.add_parser("selftest")
    args = parser.parse_args(argv)
    try:
        if args.command == "selftest":
            return selftest()
        result = check(args.root)
    except Exception as exc:  # fail closed on any unexpected input
        print("WALLPAPER_CHECK FAIL gate_error=" + type(exc).__name__)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"WALLPAPER_CHECK {result['status']} problems={len(result['problems'])}")
        for problem in result["problems"]:
            print("  " + problem)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
