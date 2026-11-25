#!/usr/bin/env python3
"""Byte-exact visual-region identity check for two 8-bit PNG captures.

Reads only PNG bytes (stdlib zlib/struct). A region passes only when every
decoded pixel, including alpha, is identical in both images. This is a
render-comparison tool, not a visual-approval or Mint-acceptance gate.
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_DIMENSION = 8192
MAX_DECODED_BYTES = 256 * 1024 * 1024
SUPPORTED_COLOR_TYPES = {2: 3, 6: 4}  # truecolour, truecolour+alpha


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (abs(estimate - left), abs(estimate - above),
                 abs(estimate - upper_left))
    if distances[0] <= distances[1] and distances[0] <= distances[2]:
        return left
    if distances[1] <= distances[2]:
        return above
    return upper_left


class PngImage:
    __slots__ = ("width", "height", "channels", "rows")

    def __init__(self, width: int, height: int, channels: int, rows: list[bytes]):
        self.width = width
        self.height = height
        self.channels = channels
        self.rows = rows

    def region_bytes(self, x: int, y: int, width: int, height: int) -> bytes:
        if min(x, y, width, height) < 0 or x + width > self.width or y + height > self.height:
            raise ValueError("region outside image bounds")
        stride = width * self.channels
        selected = self.rows[y:y + height]
        if len(selected) != height or any(len(row) != self.width * self.channels
                                          for row in selected):
            raise ValueError("region rows are incomplete")
        return b"".join(row[x * self.channels:(x + width) * self.channels]
                        for row in selected)


def decode_png(path: Path) -> PngImage:
    """Decode a bounded 8-bit non-interlaced RGB/RGBA PNG with verified CRCs."""
    data = path.read_bytes()
    if data[:8] != PNG_SIGNATURE:
        raise ValueError("PNG signature missing")
    offset = 8
    compressed: list[bytes] = []
    width = height = channels = None
    ended = False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 8 + length
        if end + 4 > len(data):
            raise ValueError("truncated PNG chunk")
        payload = data[offset + 8:end]
        expected_crc = struct.unpack_from(">I", data, end)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != expected_crc:
            raise ValueError("PNG checksum mismatch")
        if kind == b"IHDR":
            if width is not None or length != 13:
                raise ValueError("invalid IHDR")
            width, height, depth, colour, method, filter_method, interlace = \
                struct.unpack(">IIBBBBB", payload)
            if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
                raise ValueError("PNG dimensions out of bounds")
            if (depth, method, filter_method, interlace) != (8, 0, 0, 0):
                raise ValueError("unsupported PNG encoding")
            if colour not in SUPPORTED_COLOR_TYPES:
                raise ValueError("unsupported PNG colour type")
            channels = SUPPORTED_COLOR_TYPES[colour]
        elif kind == b"IDAT":
            compressed.append(payload)
        elif kind == b"IEND":
            if payload or end + 4 != len(data):
                raise ValueError("unexpected bytes at PNG end")
            ended = True
            break
        offset = end + 4
    if width is None or not compressed or not ended:
        raise ValueError("incomplete PNG")
    stride = width * channels
    expected = height * (stride + 1)
    if expected > MAX_DECODED_BYTES:
        raise ValueError("decoded PNG exceeds byte budget")
    raw = zlib.decompress(b"".join(compressed))
    if len(raw) != expected:
        raise ValueError("unexpected PNG scanline size")
    previous = bytearray(stride)
    rows: list[bytes] = []
    for y in range(height):
        base = y * (stride + 1)
        filter_type = raw[base]
        line = bytearray(raw[base + 1:base + stride + 1])
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(left, previous[i],
                                            previous[i - channels]
                                            if i >= channels else 0)) & 0xFF
        else:
            raise ValueError("unsupported PNG filter")
        rows.append(bytes(line))
        previous = line
    return PngImage(width, height, channels, rows)


def compare_regions(base: PngImage, feature: PngImage,
                    regions: list[tuple[int, int, int, int]]) -> dict:
    """Return exact byte-equality and differing-pixel counts per region."""
    if (base.width, base.height, base.channels) != \
            (feature.width, feature.height, feature.channels):
        raise ValueError("image dimensions or colour types differ")
    results = []
    for x, y, width, height in regions:
        before = base.region_bytes(x, y, width, height)
        after = feature.region_bytes(x, y, width, height)
        differing = sum(1 for i in range(0, len(before), base.channels)
                        if before[i:i + base.channels] != after[i:i + base.channels])
        results.append({
            "region": [x, y, width, height],
            "identical": before == after,
            "differing_pixels": differing,
        })
    return {
        "size": [base.width, base.height],
        "channels": base.channels,
        "regions": results,
        "verdict": "PASS" if all(r["identical"] for r in results) else "FAIL",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--feature", type=Path, required=True)
    parser.add_argument("--region", action="append", default=[],
                        help="x,y,width,height (repeatable; default: full frame)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        base = decode_png(args.base)
        feature = decode_png(args.feature)
        regions = []
        for value in args.region:
            parts = value.split(",")
            if len(parts) != 4:
                raise ValueError("region must be x,y,width,height")
            regions.append(tuple(int(part) for part in parts))
        if not regions:
            regions = [(0, 0, base.width, base.height)]
        result = compare_regions(base, feature, regions)
    except (OSError, ValueError, zlib.error) as exc:
        print("VISUAL_REGION_IDENTITY_BLOCKED: " + str(exc))
        return 2
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        for item in result["regions"]:
            print("REGION %s identical=%s differing_pixels=%d" %
                  (item["region"], item["identical"], item["differing_pixels"]))
        print("VISUAL_REGION_IDENTITY " + result["verdict"])
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
