#!/usr/bin/env python3
"""Validate CI screenshot dimensions and PNG integrity without external packages."""
import argparse
import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def verify_png(path: Path, width: int, height: int) -> None:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("PNG signature missing")
    cursor = len(PNG_SIGNATURE)
    found_ihdr = False
    found_data = False
    ended = False
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        length = struct.unpack_from(">I", data, cursor)[0]
        kind = data[cursor + 4:cursor + 8]
        end = cursor + 12 + length
        if end > len(data):
            raise ValueError("PNG chunk exceeds file")
        payload = data[cursor + 8:cursor + 8 + length]
        expected_crc = struct.unpack_from(">I", data, cursor + 8 + length)[0]
        actual_crc = zlib.crc32(kind + payload) & 0xffffffff
        if actual_crc != expected_crc:
            raise ValueError("PNG checksum mismatch")
        if not found_ihdr:
            if kind != b"IHDR" or length != 13:
                raise ValueError("Missing first IHDR chunk")
            actual_width, actual_height = struct.unpack_from(">II", payload)
            if (actual_width, actual_height) != (width, height):
                raise ValueError(
                    f"Expected {width}x{height}; got {actual_width}x{actual_height}"
                )
            found_ihdr = True
        if kind == b"IDAT" and payload:
            found_data = True
        cursor = end
        if kind == b"IEND":
            if payload or cursor != len(data):
                raise ValueError("Unexpected bytes at PNG end")
            ended = True
            break
    if not (found_ihdr and found_data and ended):
        raise ValueError("Incomplete PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("width", type=int)
    parser.add_argument("height", type=int)
    args = parser.parse_args()
    try:
        verify_png(args.path, args.width, args.height)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(f"PASS: valid PNG {args.width}x{args.height}: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
