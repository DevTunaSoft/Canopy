#!/usr/bin/env python3
"""Inspect approved Canopy PNG masters without changing any source pixels.

The report is an objective edge-energy *heuristic* for optical imbalance,
NOT an automatic icon recenter, a visual approval or a Qt build test.
No external Python modules are required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib


SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_FILE_BYTES = 12_000_000
MAX_PIXELS = 4_000_000
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
RELATIVE = re.compile(r"icons/[A-Za-z0-9_-]+\.png\Z")


class AuditError(ValueError):
    """Cannot safely audit a user-approved master image."""


def decode_rgba_png(blob):
    """Decode bounded noninterlaced 8-bit RGBA PNG using only stdlib."""
    if not isinstance(blob, bytes) or len(blob) > MAX_FILE_BYTES:
        raise AuditError("PNG exceeds file limit")
    if not blob.startswith(SIGNATURE):
        raise AuditError("invalid PNG signature")
    cursor = len(SIGNATURE)
    header = None
    compressed = bytearray()
    seen_end = False
    while cursor < len(blob):
        if len(blob) - cursor < 12:
            raise AuditError("truncated PNG chunk")
        size = struct.unpack_from(">I", blob, cursor)[0]
        kind = blob[cursor + 4:cursor + 8]
        end = cursor + 12 + size
        if end > len(blob):
            raise AuditError("PNG chunk exceeds file")
        payload = blob[cursor + 8:cursor + 8 + size]
        expected = struct.unpack_from(">I", blob, cursor + 8 + size)[0]
        if (zlib.crc32(kind + payload) & 0xffffffff) != expected:
            raise AuditError("PNG CRC mismatch")
        if header is None:
            if kind != b"IHDR" or size != 13:
                raise AuditError("first chunk must be IHDR")
            width, height, depth, mode, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if (width < 32 or height < 32 or width * height > MAX_PIXELS
                    or depth != 8 or mode != 6
                    or compression != 0 or filtering != 0 or interlace != 0):
                raise AuditError("unsupported dimensions or PNG encoding")
            header = (width, height)
        elif kind == b"IHDR":
            raise AuditError("duplicate IHDR")
        if kind == b"IDAT":
            compressed.extend(payload)
            if len(compressed) > MAX_FILE_BYTES:
                raise AuditError("compressed PNG payload exceeds limit")
        if kind == b"IEND":
            if payload or cursor + 12 != len(blob):
                raise AuditError("invalid PNG end")
            seen_end = True
            break
        cursor = end
    if header is None or not seen_end or not compressed:
        raise AuditError("incomplete PNG")
    width, height = header
    stride = width * 4
    expected_length = (stride + 1) * height
    try:
        stream = zlib.decompressobj()
        raw = stream.decompress(bytes(compressed), expected_length + 1)
        if (len(raw) != expected_length or not stream.eof
                or stream.unused_data or stream.unconsumed_tail):
            raise AuditError("unexpected PNG decompressed size")
    except zlib.error as exc:
        raise AuditError("malformed PNG compressed stream") from exc

    result = bytearray(stride * height)
    prior = bytearray(stride)
    pos = 0
    for y in range(height):
        filtering = raw[pos]
        pos += 1
        row = bytearray(raw[pos:pos + stride])
        pos += stride
        if filtering > 4:
            raise AuditError("unsupported PNG row filter")
        for x in range(stride):
            left = row[x - 4] if x >= 4 else 0
            above = prior[x]
            upper_left = prior[x - 4] if x >= 4 else 0
            if filtering == 1:
                predictor = left
            elif filtering == 2:
                predictor = above
            elif filtering == 3:
                predictor = (left + above) // 2
            elif filtering == 4:
                prediction = left + above - upper_left
                distances = (abs(prediction - left),
                             abs(prediction - above),
                             abs(prediction - upper_left))
                predictor = (left, above, upper_left)[distances.index(min(distances))]
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        result[y * stride:(y + 1) * stride] = row
        prior = row
    return width, height, result


def edge_centroid(width, height, rgba):
    """Approximate center of high-contrast illustration detail.

    This cannot isolate a penguin from a colorful background, so the result
    must never automatically translate/recolor/replace approved artwork.
    """
    greys = [0] * (width * height)
    for i in range(width * height):
        start = i * 4
        r, g, b, a = rgba[start:start + 4]
        greys[i] = (r * 30 + g * 59 + b * 11) // 100 if a >= 32 else 0
    margin_x = max(1, round(width * .045))
    margin_y = max(1, round(height * .045))
    weighted_x = weighted_y = total = 0
    for y in range(margin_y, height - margin_y):
        for x in range(margin_x, width - margin_x):
            index = y * width + x
            if rgba[4 * index + 3] < 32:
                continue
            strength = (
                abs(greys[index] - greys[index - 1]) +
                abs(greys[index] - greys[index - width])
            )
            weighted_x += strength * x
            weighted_y += strength * y
            total += strength
    if total == 0:
        raise AuditError("image contains no measurable edge detail")
    center_x = weighted_x / total
    center_y = weighted_y / total
    return {
        "edge_center_x": round(center_x, 2),
        "edge_center_y": round(center_y, 2),
        "offset_x_percent": round(100 * (center_x - (width - 1) / 2) / width, 2),
        "offset_y_percent": round(100 * (center_y - (height - 1) / 2) / height, 2),
    }


def audit_art(approved_dir, manifest_path):
    """Require all eight original SHA-locked PNGs; no mutations or replacements."""
    root = Path(approved_dir)
    manifest_path = Path(manifest_path)
    if (not root.is_dir() or root.is_symlink() or
            not manifest_path.is_file() or manifest_path.is_symlink()):
        raise AuditError("approved directory and manifest must be regular paths")
    if manifest_path.stat().st_size > 24_000:
        raise AuditError("manifest too large")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError("invalid manifest JSON") from exc
    rows = manifest.get("icons") if isinstance(manifest, dict) else None
    if not isinstance(rows, list) or len(rows) != 8:
        raise AuditError("expected exactly eight approved icons")
    results = []
    seen_ids = set()
    seen_paths = set()
    for row in rows:
        if not isinstance(row, dict):
            raise AuditError("invalid icon descriptor")
        name = row.get("name")
        relative = row.get("path")
        digest = row.get("sha256")
        if (not isinstance(name, str) or not re.fullmatch("[A-Za-z]+", name)
                or name in seen_ids
                or not isinstance(relative, str) or not RELATIVE.fullmatch(relative)
                or relative in seen_paths
                or not isinstance(digest, str) or not HEX64.fullmatch(digest)):
            raise AuditError("invalid or duplicated source icon entry")
        seen_ids.add(name)
        seen_paths.add(relative)
        icon = root / relative
        if not icon.is_file() or icon.is_symlink() or icon.stat().st_size > MAX_FILE_BYTES:
            raise AuditError("missing, linked or oversized master: " + name)
        blob = icon.read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise AuditError("SHA-256 mismatch: " + name)
        width, height, rgba = decode_rgba_png(blob)
        result = edge_centroid(width, height, rgba)
        results.append({
            "icon": name,
            "width": width,
            "height": height,
            **result,
        })
    return {
        "kind": "heuristic-optical-balance-review",
        "source_bytes_unchanged": True,
        "all_sha256_verified": True,
        "human_visual_approval_required": True,
        "method": "central 91% grayscale edge-energy centroid; not object detection",
        "icons": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-art-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="optional JSON report")
    args = parser.parse_args(argv)
    try:
        result = audit_art(args.approved_art_dir, args.manifest)
        formatted = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.write_text(formatted, encoding="utf-8")
        else:
            print(formatted, end="")
    except (AuditError, OSError) as exc:
        print(f"CANOPY_ICON_OPTICS_FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
