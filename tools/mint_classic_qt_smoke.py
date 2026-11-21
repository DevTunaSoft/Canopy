#!/usr/bin/env python3
"""Run non-destructive Classic Qt screenshot smoke tests in a REAL Mint guest.

Does not install software, alter display manager, replace Cinnamon, restart a
compositor, or approve visuals. Outputs a privacy-minimized JSON evidence file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

from tools.mint_guest_preflight import collect as mint_preflight

SIZES = ((1920, 1080), (1200, 750), (760, 500))
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED_MARKERS = (
    "SELF_TEST_PASS: all eight exact approved dock PNGs loaded",
    "SELF_TEST_PASS: dock icons horizontally/vertically centred",
    "SELF_TEST_PASS: nonuniform window screenshot captured",
)


class MintSmokeError(ValueError):
    """Safety gate prevents a Mint guest smoke run."""


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_resource(path, kind, *, directory=False, executable=False):
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink()
            or (not path.is_dir() if directory else not path.is_file())):
        raise MintSmokeError(kind + " must be an existing absolute, non-symlink path")
    if executable and not (path.stat().st_mode & 0o111):
        raise MintSmokeError("compiled Qt binary is not executable")
    return path


def png_size(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise MintSmokeError("screenshot missing or unsafe")
    size = path.stat().st_size
    if size < 100 or size > 40_000_000:
        raise MintSmokeError("screenshot file outside safe size limits")
    with path.open("rb") as stream:
        data = stream.read(33)
    if (len(data) < 33 or data[:8] != PNG_SIGNATURE
            or struct.unpack_from(">I", data, 8)[0] != 13
            or data[12:16] != b"IHDR"):
        raise MintSmokeError("screenshot is not a PNG with an IHDR header")
    width, height = struct.unpack_from(">II", data, 16)
    if width < 1 or height < 1 or width > 3840 or height > 2160:
        raise MintSmokeError("unexpected PNG screenshot dimensions")
    return width, height


def run_mint_smoke(*, binary, approved_art, wallpaper, output_dir, source_sha,
                   terminal=None, framing_review=False, preflight=None,
                   timeout_seconds=25):
    """Return a report after 3 Qt screenshot runs; never change system session."""
    conditions = mint_preflight() if preflight is None else preflight
    if (not isinstance(conditions, dict)
            or conditions.get("status") != "READY_FOR_TESTS"
            or conditions.get("mint_identified") is not True):
        raise MintSmokeError("real Linux Mint desktop preflight required")
    if not isinstance(source_sha, str) or not SHA40.fullmatch(source_sha):
        raise MintSmokeError("source commit must be a 40-character lowercase SHA")
    if not 2 <= timeout_seconds <= 60:
        raise MintSmokeError("timeout must be between 2 and 60 seconds")
    executable = safe_resource(binary, "Classic Qt binary", executable=True)
    art = safe_resource(approved_art, "approved art", directory=True)
    background = safe_resource(wallpaper, "alpine wallpaper")
    terminal_image = (safe_resource(terminal, "Terminal candidate")
                      if terminal is not None else None)
    target = Path(output_dir)
    if (not target.is_absolute() or target.is_symlink() or target.exists()
            or target.parent.is_symlink() or not target.parent.is_dir()):
        raise MintSmokeError("output must be a new absolute directory under an existing real parent")
    target.mkdir(mode=0o700, exist_ok=False)
    binary_hash = file_sha256(executable)
    report = {
        "schema_version": 1,
        "environment": "linuxmint",
        "qt_smoke": "FAIL",
        "mint_guest_acceptance": "PARTIAL_SMOKE_ONLY",
        "real_application_launch": "NOT_RUN",
        "compositor_session_switching": "NOT_RUN",
        "visual_owner_approval": "NOT_RUN",
        "declared_source_sha": source_sha,
        "verified_binary_sha256": binary_hash,
        "framing_review": bool(framing_review),
        "tests": [],
    }

    for width, height in SIZES:
        label = f"{width}x{height}"
        screenshot = target / ("qt-" + label + ".png")
        command = [
            str(executable),
            "--approved-art-dir", str(art),
            "--landscape-wallpaper", str(background),
            "--self-test-approved", "--self-test-size", label,
            "--self-test-screenshot", str(screenshot),
        ]
        if terminal_image is not None:
            command.extend(("--terminal-refinement", str(terminal_image)))
        if framing_review:
            command.append("--icon-framing-review")
        result = {
            "resolution": label,
            "status": "FAIL",
            "screenshot": screenshot.name,
            "exit_code": None,
            "markers_observed": 0,
        }
        try:
            process = subprocess.run(
                command, timeout=timeout_seconds, capture_output=True,
                text=True, errors="replace", check=False,
            )
            result["exit_code"] = process.returncode
            log = process.stdout + process.stderr
            result["markers_observed"] = log.count("SELF_TEST_PASS:")
            marker_ok = all(marker in log for marker in REQUIRED_MARKERS)
            if framing_review:
                marker_ok = marker_ok and (
                    "SELF_TEST_PASS: opt-in icon source framing verified" in log)
            if process.returncode == 0 and marker_ok:
                actual = png_size(screenshot)
                if actual == (width, height):
                    result["status"] = "PASS"
                    result["screenshot_sha256"] = file_sha256(screenshot)
        except (OSError, subprocess.TimeoutExpired, MintSmokeError):
            # Do not persist process stdout/stderr; Qt errors may contain
            # private filesystem paths or environment details.
            result["status"] = "FAIL"
        report["tests"].append(result)

    if all(item["status"] == "PASS" for item in report["tests"]):
        report["qt_smoke"] = "PASS"
    (target / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--approved-art-dir", type=Path, required=True)
    parser.add_argument("--landscape-wallpaper", type=Path, required=True)
    parser.add_argument("--terminal-refinement", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--icon-framing-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_mint_smoke(
            binary=args.binary, approved_art=args.approved_art_dir,
            wallpaper=args.landscape_wallpaper, terminal=args.terminal_refinement,
            output_dir=args.output_dir, source_sha=args.source_sha,
            framing_review=args.icon_framing_review,
        )
    except (MintSmokeError, OSError) as exc:
        print("MINT_CLASSIC_SMOKE_BLOCKED:", exc, file=sys.stderr)
        return 2
    print("MINT_CLASSIC_QT_SMOKE_" + report["qt_smoke"])
    return 0 if report["qt_smoke"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
