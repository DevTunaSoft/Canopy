#!/usr/bin/env python3
"""Fail-closed gate for the reproducible Classic UCRT64 build evidence bundle.

Usage:
    python tools/qa/classic_build_gate.py verify --evidence DIR [--source-sha SHA]
    python tools/qa/classic_build_gate.py selftest [--keep]

The verify mode reads only the evidence directory: it never builds, never
contacts the network and never trusts a hash without recomputing it. Every
check prints ``CHECK <CODE> PASS|FAIL <detail>``; a failing run prints
``FIRST <CODE>`` and exits 1. Selftest generates a synthetic bundle, proves it
green, then applies pinned negative controls and proves each one red.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tempfile
import zlib

SCHEMA_VERSION = 1
EXPECTED_SOURCE_SHA = "b31c995a650202b66c08064a7cc3b7b4f0609d2d"
SIZES = ((1920, 1080), (1200, 750), (760, 500))
BINARY_REL = "binary/canopy-classic-spike.exe"
MANIFEST_NAME = "artifact_manifest.json"
EVIDENCE_NAME = "evidence.json"
TOOLCHAIN_NAME = "toolchain.txt"
COMMANDS_NAME = "commands.txt"
CAPABILITY_LOG = "selftest-capability.log"
OPTIN_LOG = "selftest-optin-refusal.log"
REQUIRED_TOOLCHAIN_KEYS = (
    "cmake", "ninja", "qt_version", "qt_install_prefix", "compiler",
    "msys_runtime", "source_date_epoch",
)
REQUIRED_COMMAND_FRAGMENTS = (
    "cmake -S", "-G Ninja", "cmake --build", "--self-test-approved",
    "--self-test-size 1920x1080", "--self-test-size 1200x750",
    "--self-test-size 760x500", "--self-test-system-apps-capability",
    "--self-test-system-apps",
)
SCREENSHOT_MARKERS = (
    "CANOPY_APPROVED_ART_VERIFIED",
    "SELF_TEST_PASS: all eight exact approved dock PNGs loaded",
    "SELF_TEST_PASS: dock icons horizontally/vertically centred",
    "SELF_TEST_PASS: desktop chrome geometry",
    "SELF_TEST_PASS: nonuniform window screenshot captured",
)
FAIL_MARKERS = ("SELF_TEST_FAIL", "_FAIL:")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 40_000_000
MAX_IDAT_BYTES = 80_000_000


class GateError(Exception):
    """Gate-level failure with a stable report code."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_rel(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise GateError("unsafe manifest path")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise GateError("unsafe manifest path")
    return candidate


def _expected_relpaths(evidence: dict) -> set:
    paths = {
        EVIDENCE_NAME, TOOLCHAIN_NAME, COMMANDS_NAME, BINARY_REL,
        CAPABILITY_LOG, OPTIN_LOG,
    }
    for shot in evidence["screenshots"]:
        paths.add(_safe_rel(shot["path"]).as_posix())
        paths.add(_safe_rel(shot["log"]).as_posix())
    return paths


def compute_manifest(root: Path, evidence: dict) -> dict:
    manifest = {}
    for rel in sorted(_expected_relpaths(evidence)):
        target = root / rel
        if not target.is_file() or target.is_symlink():
            raise GateError("manifest file missing: " + rel)
        manifest[rel] = sha256_file(target)
    return manifest


def write_manifest(root: Path, evidence: dict) -> dict:
    manifest = compute_manifest(root, evidence)
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _png_pixels(path: Path) -> tuple:
    """Parse bounded 8-bit non-interlaced RGB/RGBA PNG; return (w, h, samples)."""
    if path.is_symlink() or not path.is_file():
        raise GateError("screenshot missing or unsafe")
    size = path.stat().st_size
    if size < 57 or size > MAX_PNG_BYTES:
        raise GateError("screenshot outside safe size limits")
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise GateError("bad PNG signature")
    offset = 8
    width = height = 0
    color_type = None
    idat = bytearray()
    seen_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if length > MAX_PNG_BYTES or offset + 12 + length > len(data):
            raise GateError("PNG chunk outside bounds")
        crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise GateError("PNG chunk CRC mismatch")
        if kind == b"IHDR":
            if width or height or len(payload) != 13:
                raise GateError("PNG IHDR invalid")
            width, height, depth, color_type, compression, filt, interlace = \
                struct.unpack(">IIBBBBB", payload)
            if depth != 8 or color_type not in (2, 6) or compression or filt or interlace:
                raise GateError("PNG format unsupported")
        elif kind == b"IDAT":
            idat.extend(payload)
            if len(idat) > MAX_IDAT_BYTES:
                raise GateError("PNG IDAT too large")
        elif kind == b"IEND":
            seen_iend = True
            break
        offset += 12 + length
    if not width or not height or not seen_iend or not idat:
        raise GateError("PNG structure incomplete")
    channels = 3 if color_type == 2 else 4
    row_bytes = width * channels
    try:
        scanlines = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise GateError("PNG decompression failed: " + type(exc).__name__) from exc
    if len(scanlines) != height * (row_bytes + 1):
        raise GateError("PNG scanline count invalid")
    previous = bytearray(row_bytes)
    samples = set()
    for row_index in range(height):
        start = row_index * (row_bytes + 1)
        filter_type = scanlines[start]
        encoded = scanlines[start + 1:start + 1 + row_bytes]
        if filter_type > 4:
            raise GateError("PNG filter invalid")
        current = bytearray(row_bytes)
        for index, value in enumerate(encoded):
            left = current[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            else:
                estimate = left + above - upper_left
                distances = (abs(estimate - left), abs(estimate - above),
                             abs(estimate - upper_left))
                if distances[0] <= distances[1] and distances[0] <= distances[2]:
                    predictor = left
                elif distances[1] <= distances[2]:
                    predictor = above
                else:
                    predictor = upper_left
            current[index] = (value + predictor) & 0xff
        if row_index % max(1, height // 8) == 0:
            for column in range(0, width, max(1, width // 8)):
                pos = column * channels
                samples.add(tuple(current[pos:pos + 3]))
        previous = current
    return width, height, samples


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise GateError("required evidence file missing")
    return path.read_text(encoding="utf-8", errors="replace")


def verify(root: Path, source_sha: str) -> int:
    checks = []

    def check(code, condition, detail):
        checks.append((code, bool(condition), detail))

    evidence_path = root / EVIDENCE_NAME
    evidence = None
    try:
        evidence = json.loads(_read_text(evidence_path))
        if not isinstance(evidence, dict) or evidence.get("schema_version") != SCHEMA_VERSION:
            raise GateError("schema mismatch")
        check("SCHEMA", True, "schema_version=%s" % SCHEMA_VERSION)
    except (GateError, ValueError, OSError) as exc:
        check("SCHEMA", False, type(exc).__name__)
        return report(checks)

    try:
        actual_source = evidence.get("source_sha")
        check("SOURCE_SHA", isinstance(actual_source, str)
              and actual_source.lower() == source_sha.lower()
              and len(actual_source) == 40, "pinned=%s actual=%s"
              % (source_sha, str(actual_source)[:40]))
        toolchain = evidence.get("toolchain")
        toolchain_text = _read_text(root / TOOLCHAIN_NAME)
        toolchain_ok = isinstance(toolchain, dict) and all(
            isinstance(toolchain.get(key), str) and toolchain[key].strip()
            and toolchain[key] in toolchain_text for key in REQUIRED_TOOLCHAIN_KEYS
        )
        check("TOOLCHAIN", toolchain_ok, "required fields recorded in toolchain.txt")
        commands_text = _read_text(root / COMMANDS_NAME)
        commands_ok = all(fragment in commands_text for fragment in REQUIRED_COMMAND_FRAGMENTS)
        check("COMMANDS", commands_ok, "cmake/ninja/self-test commands recorded")
        repro = evidence.get("reproducibility")
        hashes = repro.get("build_hashes") if isinstance(repro, dict) else None
        binary_sha = evidence.get("binary_sha256")
        repro_ok = (isinstance(hashes, list) and len(hashes) >= 2
                    and all(isinstance(item, str) and len(item) == 64 for item in hashes)
                    and len(set(hashes)) == 1 and hashes[0] == binary_sha)
        check("REPRO_HASHES", repro_ok, "build_hashes=%d binary_sha256=%s"
              % (len(hashes) if isinstance(hashes, list) else 0,
                 str(binary_sha)[:12]))
    except (GateError, OSError) as exc:
        check("TOOLCHAIN", False, type(exc).__name__)
        return report(checks)

    manifest = None
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
        expected = _expected_relpaths(evidence)
        keys = set(manifest.keys())
        check("MANIFEST_KEYS", isinstance(manifest, dict) and keys == expected,
              "expected=%d actual=%d" % (len(expected), len(keys)))
        for rel in keys:
            _safe_rel(rel)
    except (GateError, ValueError, OSError, AttributeError) as exc:
        check("MANIFEST_KEYS", False, type(exc).__name__)
        return report(checks)

    binary_path = root / BINARY_REL
    binary_ok = False
    try:
        binary_ok = (binary_path.is_file() and not binary_path.is_symlink()
                     and binary_path.read_bytes()[:2] == b"MZ"
                     and sha256_file(binary_path) == evidence.get("binary_sha256")
                     and manifest.get(BINARY_REL) == evidence.get("binary_sha256"))
        check("BINARY", binary_ok, "sha256=%s" % str(evidence.get("binary_sha256"))[:12])
    except OSError as exc:
        check("BINARY", False, type(exc).__name__)

    hashes_ok = True
    for rel, recorded in manifest.items():
        try:
            current = sha256_file(root / _safe_rel(rel))
            if current != recorded:
                hashes_ok = False
        except (GateError, OSError):
            hashes_ok = False
    check("FILE_HASHES", hashes_ok, "recomputed %d manifest entries" % len(manifest))

    shots_ok = True
    shot_detail = []
    for shot in evidence.get("screenshots", []):
        rel = shot.get("path")
        try:
            width, height, samples = _png_pixels(root / _safe_rel(rel))
            ok = ((width, height) == (shot.get("width"), shot.get("height"))
                  and len(samples) >= 8)
            shots_ok = shots_ok and ok
            shot_detail.append("%dx%d colors=%d" % (width, height, len(samples)))
        except (GateError, OSError, TypeError) as exc:
            shots_ok = False
            shot_detail.append(type(exc).__name__)
    expected_sizes = {(w, h) for w, h in SIZES}
    reported_sizes = {(s.get("width"), s.get("height"))
                      for s in evidence.get("screenshots", [])
                      if isinstance(s, dict)}
    check("SCREENSHOTS", shots_ok and reported_sizes == expected_sizes,
          "; ".join(shot_detail))

    logs_ok = True
    log_detail = []
    for shot in evidence.get("screenshots", []):
        try:
            text = _read_text(root / _safe_rel(shot["log"]))
            missing = [marker for marker in SCREENSHOT_MARKERS if marker not in text]
            forbidden = [marker for marker in FAIL_MARKERS if marker in text]
            ok = not missing and not forbidden
            logs_ok = logs_ok and ok
            log_detail.append("%s:%s" % (shot["log"], "ok" if ok else "missing=%d" % len(missing)))
        except (GateError, KeyError, OSError, TypeError) as exc:
            logs_ok = False
            log_detail.append(type(exc).__name__)
    check("SELFTEST_LOGS", logs_ok, "; ".join(log_detail))

    try:
        capability = _read_text(root / CAPABILITY_LOG)
        check("CAPABILITY_LOG", "CANOPY_GIO_DISABLED" in capability,
              "UCRT64 build reports no gio-unix-2.0 launcher")
    except (GateError, OSError) as exc:
        check("CAPABILITY_LOG", False, type(exc).__name__)
    try:
        optin = _read_text(root / OPTIN_LOG)
        check("OPTIN_LOG", "SYSTEM_APP_LAUNCH_TEST_PASS" in optin,
              "arbitrary launch refused without opt-in")
    except (GateError, OSError) as exc:
        check("OPTIN_LOG", False, type(exc).__name__)
    return report(checks)


def report(checks) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    for code, ok, detail in checks:
        print("CHECK %s %s %s" % (code, "PASS" if ok else "FAIL", detail))
    failed = len(checks) - passed
    print("SUMMARY checks=%d pass=%d fail=%d" % (len(checks), passed, failed))
    if failed:
        first = next(code for code, ok, _ in checks if not ok)
        print("FIRST %s" % first)
        print("VERDICT FAIL")
        return 1
    print("VERDICT PASS")
    return 0


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def make_png(width: int, height: int, uniform: bool = False) -> bytes:
    """Bounded RGB PNG generator for synthetic gate fixtures."""
    rows = bytearray()
    for y in range(height):
        color = (16, 32, 48) if uniform else (16 + (y % 16) * 11, 40 + (y % 8) * 9, 72)
        rows.extend(b"\x00" + bytes(color) * width)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (PNG_SIGNATURE + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(rows), 6))
            + _chunk(b"IEND", b""))


def make_bundle(root: Path, *, source_sha: str = EXPECTED_SOURCE_SHA) -> dict:
    """Create a small, fully valid synthetic evidence bundle."""
    (root / "binary").mkdir(parents=True, exist_ok=True)
    (root / "screenshots").mkdir(parents=True, exist_ok=True)
    binary = root / BINARY_REL
    binary.write_bytes(b"MZ" + bytes(range(256)) * 8)
    toolchain = {
        "cmake": "CMake version 4.5.1", "ninja": "1.13.2",
        "qt_version": "6.12.0", "qt_install_prefix": "C:/msys64/ucrt64",
        "compiler": "g++.exe (Rev7, Built by MSYS2 project) 16.2.0",
        "msys_runtime": "msys2-runtime 3.6.10-5", "source_date_epoch": "0",
    }
    (root / TOOLCHAIN_NAME).write_text(
        "\n".join("%s: %s" % (key, value) for key, value in toolchain.items()) + "\n",
        encoding="utf-8")
    commands = "\n".join([
        "cmake -S <source>/prototype/classic -B <out>/build -G Ninja -DCMAKE_BUILD_TYPE=Release",
        "cmake --build <out>/build --parallel 2",
        "<binary> --self-test-system-apps-capability",
        "<binary> --enable-system-apps --self-test-system-apps",
    ] + ["<binary> --approved-art-dir <art> --self-test-approved --self-test-size %dx%d --self-test-screenshot <shot>" % (w, h)
         for w, h in SIZES] + [""])
    (root / COMMANDS_NAME).write_text(commands, encoding="utf-8")
    (root / CAPABILITY_LOG).write_text("CANOPY_GIO_DISABLED\n", encoding="utf-8")
    (root / OPTIN_LOG).write_text(
        "SYSTEM_APP_LAUNCH_TEST_PASS: unknown or dangerous actions refused, no application executed\n",
        encoding="utf-8")
    binary_sha = sha256_file(binary)
    screenshots = []
    for width, height in SIZES:
        rel = "screenshots/classic-%dx%d.png" % (width, height)
        log = "selftest-%dx%d.log" % (width, height)
        (root / rel).write_bytes(make_png(width, height))
        (root / log).write_text(
            "CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and legacy blue wave\n"
            + "SELF_TEST_PASS: all eight exact approved dock PNGs loaded\n"
            + "SELF_TEST_PASS: dock icons horizontally/vertically centred count 8\n"
            + "SELF_TEST_PASS: desktop chrome geometry QSize(%d, %d)\n" % (width, height)
            + "SELF_TEST_PASS: nonuniform window screenshot captured QSize(%d, %d)\n"
            % (width, height), encoding="utf-8")
        screenshots.append({"path": rel, "log": log, "width": width, "height": height,
                            "sha256": sha256_file(root / rel)})
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "source_sha": source_sha,
        "source_tree_sha": "0" * 40,
        "toolchain": toolchain,
        "binary_sha256": binary_sha,
        "binary_size": binary.stat().st_size,
        "reproducibility": {"source_date_epoch": "0", "build_hashes": [binary_sha, binary_sha]},
        "commands": [line for line in commands.splitlines() if line],
        "screenshots": screenshots,
    }
    (root / EVIDENCE_NAME).write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_manifest(root, evidence)
    return evidence


def remanifest(root: Path) -> None:
    evidence = json.loads((root / EVIDENCE_NAME).read_text(encoding="utf-8"))
    write_manifest(root, evidence)


def selftest(keep: bool = False) -> int:
    base = Path(tempfile.mkdtemp(prefix="classic-build-gate-"))
    cases = []

    def run(label, expected_first):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = verify(base / "case", EXPECTED_SOURCE_SHA)
        text = buffer.getvalue()
        first = next((line.split()[1] for line in text.splitlines()
                      if line.startswith("FIRST ")), "NONE")
        cases.append((label, expected_first, first, rc))
        return text

    try:
        case = base / "case"
        make_bundle(case)
        text = run("green", "NONE")
        if "VERDICT PASS" not in text:
            print("SELFTEST FAIL green bundle did not pass")
            return 1

        mutations = [
            ("source", "SOURCE_SHA", lambda d: _edit_json(d, "source_sha", "1" * 40)),
            ("toolchain", "TOOLCHAIN", lambda d: _edit_text(d / TOOLCHAIN_NAME, "cmake: CMake version 4.5.1", "cmake: wrong")),
            ("repro", "REPRO_HASHES", lambda d: _edit_json(d, "reproducibility", {
                "source_date_epoch": "0", "build_hashes": ["2" * 64, "3" * 64]})),
            ("binary-manifest", "BINARY", lambda d: _edit_manifest(d, BINARY_REL, "4" * 64)),
            ("manifest-path", "MANIFEST_KEYS", lambda d: _edit_manifest_key(d, "../escape")),
            ("file-hash", "FILE_HASHES", lambda d: _edit_text(d / "selftest-1200x750.log", "CANOPY_APPROVED_ART_VERIFIED", "CANOPY_APPROVED_ART_VERIFIED\n# scratch mutation")),
            ("missing-marker", "SELFTEST_LOGS", lambda d: (_edit_text(d / "selftest-1920x1080.log", "SELF_TEST_PASS: nonuniform window screenshot captured", ""), remanifest(d))),
            ("wrong-size", "SCREENSHOTS", lambda d: (_replace_png(d, "screenshots/classic-1200x750.png", 800, 500), remanifest(d))),
            ("uniform", "SCREENSHOTS", lambda d: (_replace_uniform(d, "screenshots/classic-760x500.png", 760, 500), remanifest(d))),
            ("capability", "CAPABILITY_LOG", lambda d: (_edit_text(d / CAPABILITY_LOG, "CANOPY_GIO_DISABLED", "CANOPY_GIO_ENABLED"), remanifest(d))),
        ]
        for label, expected, mutate in mutations:
            shutil.rmtree(case)
            make_bundle(case)
            mutate(case)
            run(label, expected)

        ok = all(first == expected and (rc == (0 if expected == "NONE" else 1))
                 for _, expected, first, rc in cases)
        for label, expected, first, rc in cases:
            print("MUTATION %s expected=%s first=%s rc=%d %s"
                  % (label, expected, first, rc, "PASS" if first == expected else "FAIL"))
        print("SUMMARY cases=%d correct=%d" % (len(cases), sum(
            1 for _, expected, first, _ in cases if first == expected)))
        return 0 if ok else 1
    finally:
        if keep:
            print("SELFTEST_DIR " + str(base))
        else:
            shutil.rmtree(base, ignore_errors=True)


def _edit_json(root: Path, key: str, value) -> None:
    path = root / EVIDENCE_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data[key] = value
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if key != "binary_sha256":
        remanifest(root)


def _edit_text(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _edit_manifest(root: Path, key: str, value: str) -> None:
    path = root / MANIFEST_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data[key] = value
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _edit_manifest_key(root: Path, key: str) -> None:
    path = root / MANIFEST_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    data[key] = data.pop(BINARY_REL)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _replace_png(root: Path, rel: str, width: int, height: int) -> None:
    (root / rel).write_bytes(make_png(width, height))


def _replace_uniform(root: Path, rel: str, width: int, height: int) -> None:
    (root / rel).write_bytes(make_png(width, height, uniform=True))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--evidence", required=True)
    verify_parser.add_argument("--source-sha", default=EXPECTED_SOURCE_SHA)
    selftest_parser = sub.add_parser("selftest")
    selftest_parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "verify":
        return verify(Path(args.evidence), args.source_sha)
    return selftest(args.keep)


if __name__ == "__main__":
    sys.exit(main())
