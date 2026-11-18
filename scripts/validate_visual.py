"""Validate structure and recorded dimensions of isolated Canopy PNG artifacts.

A structural check, not visual regression approval or privacy certification.
"""
import argparse
import json
from pathlib import Path
import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 10_000_000
REQUIRED = {"top-bar", "dock"}


def png_dimensions(path):
    path = Path(path)
    if path.stat().st_size > MAX_PNG_BYTES:
        raise ValueError("PNG exceeds size limit")
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("Bad PNG signature")
    offset, ihdr, idat, ended = len(PNG_SIGNATURE), None, False, False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        name = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if length > MAX_PNG_BYTES or end > len(data):
            raise ValueError("Invalid PNG chunk length")
        payload = data[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        if zlib.crc32(name + payload) & 0xffffffff != expected_crc:
            raise ValueError("Invalid PNG CRC")
        if ihdr is None:
            if name != b"IHDR" or length != 13:
                raise ValueError("Missing IHDR")
            ihdr = struct.unpack_from(">II", payload)
            if not all(0 < dimension <= 8192 for dimension in ihdr):
                raise ValueError("Unbounded PNG dimensions")
        elif name == b"IHDR":
            raise ValueError("Duplicate IHDR")
        if name == b"IDAT":
            idat = True
        if name == b"IEND":
            if length != 0 or not idat or end != len(data):
                raise ValueError("Malformed PNG ending")
            ended = True
            break
        offset = end
    if not ended:
        raise ValueError("Missing complete PNG")
    return ihdr


def validate(directory):
    directory = Path(directory)
    report = json.loads((directory / "captures.json").read_text(encoding="utf-8"))
    if report.get("schema_version") != 1 or report.get("mode") != "isolated-xvfb":
        raise ValueError("Unexpected capture mode or schema")
    if report.get("status") != "PASS" or not isinstance(report.get("captures"), list):
        raise ValueError("Capture report is not successful")
    rows = report["captures"]
    if len(rows) != 2 or {row.get("role") for row in rows} != REQUIRED:
        raise ValueError("Unexpected captured window roles")
    for row in rows:
        role = row["role"]
        if row.get("filename") != role + ".png":
            raise ValueError("Unexpected screenshot filename")
        dimensions = png_dimensions(directory / row["filename"])
        if dimensions != (row.get("width"), row.get("height")):
            raise ValueError("PNG dimensions differ from report")
    return {"status": "PASS", "validated": sorted(REQUIRED),
            "note": "Only PNG structure/dimensions checked; no image-difference assertion"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = validate(args.directory)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
