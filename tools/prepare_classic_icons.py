#!/usr/bin/env python3
"""Stage *reviewed* Canopy Classic PNG icons without substituting prototype SVGs.

This is an offline packaging utility, NOT automatic approval or runtime integration.
Requires independently prepared RGBA sources for each exact user-selected option.
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
import sys
import zlib
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "prototype/classic/assets/icons/classic-approved-selections.json"
PNG_SIGNATURE = b"\\x89PNG\\r\\n\\x1a\\n"
MAX_PNG_SIZE = 4 * 1024 * 1024
MIN_DIMENSION = 256
MAX_DIMENSION = 2048


def validate_png(path):
    """Require a structurally intact, bounded 8-bit RGBA PNG."""
    raw = path.read_bytes()
    if len(raw) > MAX_PNG_SIZE or len(raw) < 57 or not raw.startswith(PNG_SIGNATURE):
        raise ValueError(f"{path.name}: invalid PNG signature or file size")
    pos = len(PNG_SIGNATURE)
    width = height = None
    seen_idat = False
    seen_iend = False
    while pos + 12 <= len(raw):
        size = struct.unpack_from(">I", raw, pos)[0]
        kind = raw[pos + 4:pos + 8]
        if size > MAX_PNG_SIZE or pos + 12 + size > len(raw):
            raise ValueError(f"{path.name}: malformed PNG chunk")
        payload = raw[pos + 8:pos + 8 + size]
        checksum = struct.unpack_from(">I", raw, pos + 8 + size)[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != checksum:
            raise ValueError(f"{path.name}: PNG CRC mismatch")
        if pos == 8 and (kind != b"IHDR" or size != 13):
            raise ValueError(f"{path.name}: missing PNG IHDR")
        if kind == b"IHDR":
            if width is not None or size != 13:
                raise ValueError(f"{path.name}: invalid or duplicate IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if not (MIN_DIMENSION <= width <= MAX_DIMENSION and MIN_DIMENSION <= height <= MAX_DIMENSION):
                raise ValueError(f"{path.name}: icon dimensions outside 256..2048")
            if (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise ValueError(f"{path.name}: expected noninterlaced 8-bit RGBA PNG")
        elif kind == b"IDAT":
            seen_idat = True
        elif kind == b"IEND":
            if size != 0:
                raise ValueError(f"{path.name}: malformed IEND")
            seen_iend = True
            pos += 12
            break
        elif kind and not (kind[0] & 32):
            # Reject unrecognized critical PNG chunks rather than quietly shipping.
            raise ValueError(f"{path.name}: unsupported critical PNG chunk")
        pos += 12 + size
    if not seen_idat or not seen_iend or pos != len(raw):
        raise ValueError(f"{path.name}: incomplete PNG")
    return (width, height)


def stage_assets(source, output):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("style") != "classic" or manifest.get("selection_state") != "user_approved_visual_reference":
        raise ValueError("The approved Classic selection manifest is missing or invalid")
    items = manifest.get("icons")
    if not isinstance(items, list) or len(items) != 8:
        raise ValueError("Expected exactly eight approved selections")
    if source.resolve() == output.resolve():
        raise ValueError("Source and output must differ")
    prepared = []
    for item in items:
        app, option = item["app"], item["option"]
        if not app.isascii() or not app.isalpha() or not 1 <= option <= 8:
            raise ValueError("Invalid app name or selection option")
        filename = f"{app}-option-{option}.png"
        path = source / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing reviewed source: {filename}")
        dimensions = validate_png(path)
        prepared.append((app, option, path, dimensions))
    if len({p[0] for p in prepared}) != 8:
        raise ValueError("Duplicate app in manifest")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty (avoid overwriting reviewed assets)")
    output.mkdir(parents=True, exist_ok=True)
    resources = ET.Element("RCC")
    prefix = ET.SubElement(resources, "qresource", prefix="/canopy/classic/icons")
    records = []
    for app, option, src, dimensions in prepared:
        destination = f"{app}.png"
        shutil.copyfile(src, output / destination)
        ET.SubElement(prefix, "file", alias=destination).text = destination
        records.append({"app": app, "option": option, "file": destination, "dimensions": list(dimensions)})
    ET.ElementTree(resources).write(output / "classic-icons.qrc", encoding="unicode", xml_declaration=True)
    (output / "staged-icons.json").write_text(
        json.dumps({"scope": "review_only_not_release_approved", "icons": records}, indent=2) + "\\n",
        encoding="utf-8",
    )
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Directory with app-option-N.png source artwork")
    parser.add_argument("--output", type=Path, required=True, help="New or empty staging directory")
    args = parser.parse_args(argv)
    try:
        staged = stage_assets(args.source, args.output)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
    print(f"STAGED {len(staged)} Classic icons for further review (not release approved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
