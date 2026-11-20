#!/usr/bin/env python3
"""Read-only source gate for the seven original Canopy Classic dock SVG icons.

Checks security and source dimensions, not whether the artwork looks premium.
"""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
ICON_NAMES = ("canopy", "files", "browser", "photos", "settings", "terminal", "trash")
TAGS = {"svg", "title", "desc", "defs", "linearGradient", "stop", "rect",
        "path", "circle", "text"}
ATTRS = {"width", "height", "viewBox", "id", "x1", "y1", "x2", "y2", "offset",
         "stop-color", "stop-opacity", "fill", "stroke", "stroke-width",
         "stroke-opacity", "fill-opacity", "opacity", "stroke-linecap",
         "stroke-linejoin", "cx", "cy", "r", "rx", "ry", "x", "y", "d",
         "font-family", "font-weight", "font-size", "text-anchor"}
LOCAL_REF = re.compile(r"^url\(#([A-Za-z][A-Za-z0-9_-]*)\)$")


def verify_icon(path: Path) -> None:
    raw = path.read_bytes()
    if len(raw) > 20_000:
        raise ValueError("Icon exceeds the bounded authored asset limit")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD and XML entities are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed icon SVG: {exc}") from exc
    if root.tag != NS + "svg" or root.get("viewBox") != "0 0 128 128":
        raise ValueError("Icon must be a namespaced 128x128 vector")
    title = root.find(NS + "title")
    if title is None or not title.text or not title.text.startswith("Canopy "):
        raise ValueError("An original Canopy title is required")

    defs = set()
    refs = []
    shapes = 0
    for element in root.iter():
        tag = element.tag.removeprefix(NS)
        if element.tag != NS + tag or tag not in TAGS:
            raise ValueError(f"Unsupported or unsafe icon element: {element.tag}")
        for key, value in element.attrib.items():
            if key not in ATTRS:
                raise ValueError(f"Unsupported icon attribute: {key}")
            if value.lower().lstrip().startswith(("http:", "https:", "data:", "javascript:")):
                raise ValueError("External or executable references are forbidden")
            if "url(" in value:
                match = LOCAL_REF.fullmatch(value)
                if not match:
                    raise ValueError("Only same-file gradient references permitted")
                refs.append(match.group(1))
        if tag == "linearGradient":
            identifier = element.get("id")
            if not identifier or identifier in defs:
                raise ValueError("Invalid or duplicate gradient name")
            defs.add(identifier)
        if tag in {"rect", "path", "circle"}:
            shapes += 1
    if shapes < 3:
        raise ValueError("Icon does not have sufficient authored geometry")
    if not set(refs).issubset(defs):
        raise ValueError("Icon uses an undefined gradient")


def verify_icon_set(root: Path) -> None:
    actual = {path.name for path in root.glob("*.svg")}
    expected = {name + ".svg" for name in ICON_NAMES}
    if actual != expected:
        raise ValueError(f"Expected exactly seven original icons; missing {sorted(expected - actual)}; unexpected {sorted(actual - expected)}")
    for name in ICON_NAMES:
        verify_icon(root / (name + ".svg"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        verify_icon_set(args.directory)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print("PASS: seven self-contained Canopy dock SVG assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
