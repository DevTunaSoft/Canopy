#!/usr/bin/env python3
"""Create a synthetic high-resolution PNG for Qt decode tests only.

The output is a deterministic color-band fixture, NOT a Canopy wallpaper
concept or an approved visual asset. Uses only the Python standard library.
"""
from pathlib import Path
import argparse
import struct
import zlib


def png_chunk(tag: bytes, payload: bytes) -> bytes:
    body = tag + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)


def write_fixture(path: Path, width: int = 2048, height: int = 1152) -> None:
    if width < 1 or height < 1 or width * height > 32_000_000:
        raise ValueError("Invalid fixture dimensions")
    path.parent.mkdir(parents=True, exist_ok=True)
    compressor = zlib.compressobj(level=6)
    compressed = bytearray()
    for y in range(height):
        # A distinct sky/foreground color difference is required by the
        # Qt screenshot integrity check; this is not photographic artwork.
        color = (84, 133, 210) if y < height // 2 else (38, 114, 79)
        compressed.extend(compressor.compress(b"\x00" + bytes(color) * width))
    compressed.extend(compressor.flush())
    header = b"\x89PNG\r\n\x1a\n"
    payload = (header
               + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
               + png_chunk(b"IDAT", bytes(compressed))
               + png_chunk(b"IEND", b""))
    path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_fixture(args.output)
    print(f"FIXTURE_CREATED: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
