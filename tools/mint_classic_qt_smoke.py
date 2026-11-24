#!/usr/bin/env python3
"""Run non-destructive Classic Qt screenshot smoke tests in a REAL Mint guest.

Does not install software, alter display manager, replace Cinnamon, restart a
compositor, or approve visuals. Outputs a privacy-minimized JSON evidence file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import struct
import subprocess
import time
import zlib
import sys

if __package__ in (None, ""):
    # Direct execution (python tools/mint_classic_qt_smoke.py) puts tools/,
    # not the repository root, on sys.path. Module-style invocation already
    # has the repository root and is intentionally left unchanged.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.mint_guest_preflight import collect as mint_preflight

SIZES = ((1920, 1080), (1200, 750), (760, 500))
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED_MARKERS = (
    "SELF_TEST_PASS: all eight exact approved dock PNGs loaded",
    "SELF_TEST_PASS: dock icons horizontally/vertically centred",
    "SELF_TEST_PASS: nonuniform window screenshot captured",
)
FRAME_MARKER = "SELF_TEST_PASS: opt-in icon source framing verified"
PNG_MAX_FILE_SIZE = 40_000_000
PNG_MAX_CHUNK_SIZE = 40_000_000
PNG_MAX_WIDTH = 3840
PNG_MAX_HEIGHT = 2160
MAX_TIMEOUT_SECONDS = 30
MAX_MARKER_LINE_BYTES = 512


class MintSmokeError(ValueError):
    """Safety gate prevents a Mint guest smoke run."""


def _open_regular_file(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MintSmokeError("file is missing or unsafe") from exc
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise MintSmokeError("file is missing or unsafe")
    return os.fdopen(descriptor, "rb")


def file_sha256(path):
    digest = hashlib.sha256()
    with _open_regular_file(path) as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _has_symlink_component(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def safe_resource(path, kind, *, directory=False, executable=False):
    path = Path(path)
    if (not path.is_absolute() or _has_symlink_component(path)
            or (not path.is_dir() if directory else not path.is_file())):
        raise MintSmokeError(kind + " must be an existing absolute, non-symlink path")
    if executable and not (path.stat().st_mode & 0o111):
        raise MintSmokeError("compiled Qt binary is not executable")
    return path


def _as_path(value, kind):
    """Convert a caller-supplied path, rejecting wrong types with a domain error."""
    if isinstance(value, str):
        return Path(value)
    if isinstance(value, os.PathLike):
        candidate = os.fspath(value)
        if isinstance(candidate, str):
            return Path(candidate)
    raise MintSmokeError(kind + " must be a str or str-returning PathLike")


def _paeth(left, above, upper_left):
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _unfilter_scanline(filter_type, encoded, previous, bytes_per_pixel):
    row = bytearray(encoded)
    if filter_type == 0:
        return row
    for index in range(len(row)):
        left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        above = previous[index] if previous is not None else 0
        upper_left = (
            previous[index - bytes_per_pixel]
            if previous is not None and index >= bytes_per_pixel else 0
        )
        if filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        else:
            predictor = _paeth(left, above, upper_left)
        row[index] = (row[index] + predictor) & 0xff
    return row


def png_size(path):
    """Verify PNG structure, decompressed scanlines and visible pixel variation.

    Only bounded-size, non-interlaced RGB/RGBA screenshots are accepted.
    """
    path = Path(path)
    if _has_symlink_component(path) or not path.is_file():
        raise MintSmokeError("screenshot missing or unsafe")
    size = path.stat().st_size
    if size < 57 or size > PNG_MAX_FILE_SIZE:
        raise MintSmokeError("screenshot file outside safe size limits")
    width = height = channels = None
    seen_ihdr = seen_idat = ended_idat = seen_plte = False
    saw_iend = False
    previous_row = None
    previous_visible_row = None
    horizontal_varied_rows = vertical_varied_rows = 0
    scanline = bytearray()
    decoded_size = row_size = 0
    decompressor = zlib.decompressobj()

    def consume_decompressed(data):
        nonlocal decoded_size, previous_row, previous_visible_row
        nonlocal horizontal_varied_rows, vertical_varied_rows
        decoded_size += len(data)
        expected = height * (row_size + 1)
        if decoded_size > expected:
            raise MintSmokeError("PNG decompressed data exceeds image dimensions")
        scanline.extend(data)
        while len(scanline) >= row_size + 1:
            filter_type = scanline[0]
            if filter_type > 4:
                raise MintSmokeError("invalid PNG scanline filter")
            encoded = bytes(scanline[1:row_size + 1])
            del scanline[:row_size + 1]
            if (horizontal_varied_rows < max(2, height // 100)
                    or vertical_varied_rows < max(2, height // 100)):
                row = _unfilter_scanline(
                    filter_type, encoded, previous_row, channels,
                )
                if channels == 4 and row[3::4].count(255) != width:
                    visible_row = bytearray()
                    for offset in range(0, row_size, channels):
                        alpha = row[offset + 3]
                        visible_row.extend(
                            (row[offset + channel] * alpha
                             + 255 * (255 - alpha) + 127) // 255
                            for channel in range(3)
                        )
                    visible_channels = 3
                else:
                    visible_row = row
                    visible_channels = channels
                if visible_row != visible_row[:visible_channels] * width:
                    horizontal_varied_rows += 1
                if (previous_visible_row is not None
                        and visible_row != previous_visible_row):
                    vertical_varied_rows += 1
                previous_visible_row = visible_row
                if (horizontal_varied_rows >= max(2, height // 100)
                        and vertical_varied_rows >= max(2, height // 100)):
                    previous_row = None
                else:
                    previous_row = row

    with _open_regular_file(path) as stream:
        if stream.read(8) != PNG_SIGNATURE:
            raise MintSmokeError("invalid PNG signature")
        while True:
            header = stream.read(8)
            if len(header) != 8:
                raise MintSmokeError("truncated PNG chunk header")
            length, kind = struct.unpack(">I4s", header)
            if length > PNG_MAX_CHUNK_SIZE:
                raise MintSmokeError("oversized PNG chunk")
            payload = stream.read(length)
            check_bytes = stream.read(4)
            if len(payload) != length or len(check_bytes) != 4:
                raise MintSmokeError("truncated PNG chunk")
            expected_crc = struct.unpack(">I", check_bytes)[0]
            if zlib.crc32(kind + payload) & 0xffffffff != expected_crc:
                raise MintSmokeError("corrupt PNG chunk CRC")
            if any(not (65 <= byte <= 90 or 97 <= byte <= 122) for byte in kind):
                raise MintSmokeError("invalid PNG chunk type")
            if 97 <= kind[2] <= 122:
                raise MintSmokeError("invalid PNG reserved chunk bit")
            if not seen_ihdr:
                if kind != b"IHDR" or length != 13:
                    raise MintSmokeError("missing PNG image header")
                width, height, depth, color, compression, filtering, interlace = (
                    struct.unpack(">IIBBBBB", payload)
                )
                if (width < 1 or height < 1
                        or width > PNG_MAX_WIDTH or height > PNG_MAX_HEIGHT
                        or depth != 8 or color not in (2, 6)
                        or compression != 0 or filtering != 0 or interlace != 0):
                    raise MintSmokeError("unsupported PNG screenshot encoding")
                channels = 3 if color == 2 else 4
                row_size = width * channels
                seen_ihdr = True
            elif kind == b"IHDR":
                raise MintSmokeError("duplicate PNG image header")
            if kind == b"IDAT":
                if ended_idat:
                    raise MintSmokeError("non-consecutive PNG image data")
                seen_idat = True
                compressed = payload
                while compressed:
                    try:
                        output = decompressor.decompress(compressed, 65536)
                    except zlib.error as exc:
                        raise MintSmokeError("corrupt PNG compressed image data") from exc
                    remaining = decompressor.unconsumed_tail
                    if decompressor.unused_data:
                        raise MintSmokeError("trailing PNG compressed image data")
                    consume_decompressed(output)
                    if remaining == compressed and not output:
                        raise MintSmokeError("invalid PNG compressed image data")
                    compressed = remaining
            elif seen_idat and kind != b"IEND":
                ended_idat = True
            if kind == b"PLTE":
                if seen_plte or seen_idat or not 3 <= length <= 768 or length % 3:
                    raise MintSmokeError("invalid PNG palette chunk")
                seen_plte = True
            if kind not in (b"IHDR", b"PLTE", b"IDAT", b"IEND") and not (kind[0] & 0x20):
                raise MintSmokeError("unsupported critical PNG chunk")
            if kind == b"IEND":
                if stream.read(1):
                    raise MintSmokeError("invalid PNG ending or trailing bytes")
                if length or not seen_idat or not decompressor.eof:
                    raise MintSmokeError("invalid PNG ending or missing image data")
                expected_size = height * (row_size + 1)
                if decoded_size != expected_size or scanline:
                    raise MintSmokeError("incomplete PNG decompressed image data")
                if (horizontal_varied_rows < max(2, height // 100)
                        or vertical_varied_rows < max(2, height // 100)):
                    raise MintSmokeError("PNG screenshot has no pixel variation")
                saw_iend = True
                break
        if not saw_iend:
            if not seen_ihdr:
                raise MintSmokeError("missing PNG image header")
            if not seen_idat:
                raise MintSmokeError("PNG has no image data")
            raise MintSmokeError("missing PNG ending")
    return width, height


def _match_marker_line(line, marker_bytes, seen_lines):
    """Return (matched marker or None, duplicate-line flag) for a pass line.

    Real Qt builds append detail after SELF_TEST_PASS markers, so matching is
    prefix-based; duplicate exact lines are still rejected.
    """
    line = line.rstrip(b"\r")
    duplicate = line in seen_lines
    seen_lines.add(line)
    for prefix, marker in marker_bytes.items():
        if line.startswith(prefix):
            return marker, duplicate
    return None, duplicate


def _register_marker(line, marker_bytes, seen_lines, counted_markers, counts):
    """Count each expected marker once, even when Qt prints detail variants."""
    marker, duplicate = _match_marker_line(line, marker_bytes, seen_lines)
    if marker is not None and marker not in counted_markers:
        counts[marker] += 1
        counted_markers.add(marker)
    return duplicate


def _run_qt(command, timeout_seconds, expected_markers):
    """Drain Qt output without retaining unbounded logs and count exact markers."""
    counts = {marker: 0 for marker in expected_markers}
    marker_lines = 0
    duplicate_marker = False
    seen_lines = set()
    counted_markers = set()
    pending = bytearray()
    discarding_line = False
    marker_bytes = {marker.encode("utf-8"): marker for marker in expected_markers}

    def record(line):
        nonlocal marker_lines, duplicate_marker
        line = line.rstrip(b"\r")
        if line.startswith(b"SELF_TEST_PASS:"):
            marker_lines += 1
            duplicate = _register_marker(
                line, marker_bytes, seen_lines, counted_markers, counts)
            if duplicate:
                duplicate_marker = True

    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True, close_fds=True,
    )

    def consume_output(chunk):
        nonlocal discarding_line
        while chunk:
            newline = chunk.find(b"\n")
            segment = chunk if newline < 0 else chunk[:newline]
            if not discarding_line:
                if len(pending) + len(segment) <= MAX_MARKER_LINE_BYTES:
                    pending.extend(segment)
                else:
                    pending.clear()
                    discarding_line = True
            if newline < 0:
                break
            if not discarding_line:
                record(bytes(pending))
            pending.clear()
            discarding_line = False
            chunk = chunk[newline + 1:]

    timed_out = False
    return_code = None
    deadline = time.monotonic() + timeout_seconds
    selector = selectors.DefaultSelector()
    try:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        eof = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError:
                    process.kill()
                process.wait()
                break
            if eof:
                if process.poll() is not None:
                    break
                time.sleep(min(remaining, 0.05))
                continue
            if selector.select(min(remaining, 0.1)):
                try:
                    output = os.read(process.stdout.fileno(), 4096)
                except BlockingIOError:
                    continue
                if output:
                    consume_output(output)
                else:
                    selector.unregister(process.stdout)
                    eof = True
        return_code = process.wait()
        if eof and pending and not discarding_line:
            record(bytes(pending))
    finally:
        selector.close()
        process.stdout.close()
    return ((None if timed_out else return_code), counts, marker_lines,
            duplicate_marker)


def _write_report(path, report):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        destination.write(json.dumps(report, indent=2, sort_keys=True) + "\n")


def run_mint_smoke(*, binary, approved_art, wallpaper, output_dir, source_sha,
                   terminal=None, framing_review=False, preflight=None,
                   timeout_seconds=25):
    """Return a report after 3 Qt screenshot runs; never change system session."""
    if type(framing_review) is not bool:
        raise MintSmokeError("framing_review must be a bool")
    binary = _as_path(binary, "Classic Qt binary")
    approved_art = _as_path(approved_art, "approved art")
    wallpaper = _as_path(wallpaper, "alpine wallpaper")
    if terminal is not None:
        terminal = _as_path(terminal, "Terminal candidate")
    output_dir = _as_path(output_dir, "output directory")
    conditions = mint_preflight() if preflight is None else preflight
    if (not isinstance(conditions, dict)
            or conditions.get("status") != "READY_FOR_TESTS"
            or conditions.get("mint_identified") is not True):
        raise MintSmokeError("real Linux Mint desktop preflight required")
    if not isinstance(source_sha, str) or not SHA40.fullmatch(source_sha):
        raise MintSmokeError("source commit must be a 40-character lowercase SHA")
    if (type(timeout_seconds) is not int
            or not 2 <= timeout_seconds <= MAX_TIMEOUT_SECONDS):
        raise MintSmokeError(
            "timeout must be an integer between 2 and "
            f"{MAX_TIMEOUT_SECONDS} seconds"
        )
    executable = safe_resource(binary, "Classic Qt binary", executable=True)
    art = safe_resource(approved_art, "approved art", directory=True)
    background = safe_resource(wallpaper, "alpine wallpaper")
    terminal_image = (safe_resource(terminal, "Terminal candidate")
                      if terminal is not None else None)
    target = Path(output_dir)
    if (not target.is_absolute() or _has_symlink_component(target)
            or target.exists() or not target.parent.is_dir()):
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
            "screenshot_sha256": None,
            "exit_code": None,
            "markers_observed": 0,
        }
        try:
            expected_markers = REQUIRED_MARKERS + ((FRAME_MARKER,) if framing_review else ())
            exit_code, marker_counts, marker_lines, duplicate_marker = _run_qt(
                command, timeout_seconds, expected_markers,
            )
            result["exit_code"] = exit_code
            result["markers_observed"] = marker_lines
            marker_ok = (
                marker_lines >= len(expected_markers)
                and not duplicate_marker
                and all(marker_counts[marker] == 1 for marker in expected_markers)
            )
            if exit_code == 0 and marker_ok:
                actual = png_size(screenshot)
                if actual == (width, height):
                    result["status"] = "PASS"
                    result["screenshot_sha256"] = file_sha256(screenshot)
        except (OSError, MintSmokeError):
            # Do not persist process stdout/stderr; Qt errors may contain
            # private filesystem paths or environment details.
            result["status"] = "FAIL"
        report["tests"].append(result)

    if all(item["status"] == "PASS" for item in report["tests"]):
        report["qt_smoke"] = "PASS"
    _write_report(target / "report.json", report)
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
