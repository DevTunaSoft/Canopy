#!/usr/bin/env python3
"""Validate redistributable Canopy SVG artwork using only the Python stdlib.

This is an asset-safety/source-quality check, NOT a visual-quality approval.
"""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
TAGS = {"svg", "title", "desc", "defs", "linearGradient", "stop", "rect", "path"}
ATTRS = {
    "width", "height", "viewBox", "id", "x1", "y1", "x2", "y2",
    "offset", "stop-color", "stop-opacity", "fill", "fill-opacity",
    "opacity", "stroke", "stroke-width", "stroke-opacity", "d",
}
LOCAL_PAINT = re.compile(r"^url\(#([A-Za-z][A-Za-z0-9_-]*)\)$")


def verify_artwork(path: Path) -> None:
    raw = path.read_bytes()
    if len(raw) > 100_000:
        raise ValueError("Artwork is unexpectedly large for a static vector")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("External entities and DTDs are prohibited")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid SVG: {exc}") from exc
    if root.tag != NS + "svg":
        raise ValueError("Expected a namespaced SVG root")
    if root.get("viewBox") != "0 0 1920 1080":
        raise ValueError("Wallpaper source must be 1920x1080 with a 16:9 viewBox")

    definitions = set()
    paths = 0
    colors = set()
    local_refs = []
    for node in root.iter():
        name = node.tag.removeprefix(NS)
        if node.tag != NS + name or name not in TAGS:
            raise ValueError(f"Forbidden SVG element: {node.tag}")
        if node.text and name not in ("title", "desc") and node.text.strip():
            raise ValueError("Unexpected text embedded in graphic primitives")
        for key, value in node.attrib.items():
            if key not in ATTRS:
                raise ValueError(f"Forbidden SVG attribute: {key}")
            if value.lstrip().lower().startswith(("http:", "https:", "data:", "javascript:")):
                raise ValueError(f"External or executable SVG value rejected: {key}")
            if "url(" in value:
                match = LOCAL_PAINT.fullmatch(value)
                if match is None:
                    raise ValueError("Only local gradient references are allowed")
                local_refs.append(match.group(1))
        if name == "linearGradient":
            identifier = node.get("id")
            if not identifier or identifier in definitions:
                raise ValueError("Gradient identifiers must be unique")
            definitions.add(identifier)
        if name == "path":
            paths += 1
            if not node.get("d", "").startswith("M"):
                raise ValueError("Path geometry missing an absolute move")
        if name == "stop" and node.get("stop-color"):
            colors.add(node.get("stop-color"))
    if paths < 8 or len(colors) < 10:
        raise ValueError("Artwork lacks the authored path/gradient detail")
    if not local_refs or not set(local_refs).issubset(definitions):
        raise ValueError("Gradient references are missing or unresolved")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artwork", type=Path)
    args = parser.parse_args()
    try:
        verify_artwork(args.artwork)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(f"PASS: static, self-contained authored SVG: {args.artwork}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
