#!/usr/bin/env python3
"""Offline QML layout-contract checks for reduced window widths.

Reads the compiled Classic QML source and verifies that its reflow contracts
hold at the smallest size the existing Mint screenshot harness already
targets (760x500): the window fits its minimums, compact mode engages, the
Files preview and dock stay inside the viewport, and overflow-prone content
is clipped/scrolled. This is source-level evidence only: it starts no Qt
process, polls nothing, and does not claim a real Mint or compiled-Qt run.
"""
from __future__ import annotations

import ast
from collections.abc import Mapping
import json
import os
import re
import sys
from pathlib import Path

from tools import check_screenshot
from tools.mint_classic_qt_smoke import SIZES, file_sha256

# Reuse the smallest resolution from the existing smoke harness rather than
# inventing a second reduced-width target.
REDUCED_SIZE = SIZES[-1]  # (760, 500)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "prototype" / "classic"

_CALLS = {"min": min, "max": max}
_LIMITER_VARIABLE = 10 ** 9  # stand-in for an unbounded implicit width


def _require_size(size, label):
    """Return a bounded numeric (width, height) pair or fail closed.

    Callers may hand in hostile-but-bounded values (a bare string, a mapping,
    a bool, numeric-looking strings). Every such value must produce this
    module's domain ``ValueError`` rather than leaking a built-in unpack,
    comparison or float-conversion exception.
    """
    if not isinstance(size, (tuple, list)) or len(size) != 2:
        raise ValueError(label + " must be a (width, height) pair")
    width, height = size
    for value in (width, height):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(label + " components must be numbers")
    return (width, height)


def _require_sources(text):
    """Return the three QML source texts or fail closed with ValueError."""
    if not isinstance(text, Mapping):
        raise ValueError("sources must be a mapping of QML texts")
    for key in ("main", "theme", "preview"):
        if key not in text:
            raise ValueError("sources missing " + key)
        if not isinstance(text[key], str):
            raise ValueError("sources[" + key + "] must be QML source text")
    return text


def _require_path(value, label):
    """Gate path-like inputs before they reach pathlib/regex helpers."""
    if not isinstance(value, (str, os.PathLike)) or isinstance(value, bytes):
        raise ValueError(label + " must be a path-like value")
    return value


def _dotted_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        raise ValueError("unsupported QML reference")
    parts.append(node.id)
    return ".".join(reversed(parts))


def evaluate(expression: str, variables: dict) -> float:
    """Evaluate a QML-style arithmetic expression without exec/eval.

    Supports numeric literals, dotted references (root.width,
    canopyTheme.barHeight), Math.min/Math.max, + - * / and parentheses.
    Anything else is rejected, so source text can never execute code.
    """
    if not isinstance(expression, str):
        raise ValueError("expression must be a string")
    if not isinstance(variables, Mapping):
        raise ValueError("variables must be a mapping")
    text = expression.strip().replace("Math.min", "min").replace("Math.max", "max")
    tree = ast.parse(text, mode="eval").body

    def visit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Attribute):
            name = _dotted_name(node)
            try:
                return variables[name]
            except (KeyError, TypeError):
                raise ValueError("unknown QML reference: " + name) from None
        if isinstance(node, ast.Name):
            if node.id in variables:
                return variables[node.id]
            if node.id in _CALLS:
                return _CALLS[node.id]
            raise ValueError("unknown QML reference: " + node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if right == 0:
                raise ValueError("division by zero in QML expression")
            return left / right
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _CALLS and not node.keywords):
            return _CALLS[node.func.id](*[visit(arg) for arg in node.args])
        raise ValueError("unsupported QML expression syntax")

    return visit(tree)


def object_block(text: str, header: str) -> str:
    """Return the brace-matched body of the QML object named by header regex."""
    match = re.search(header, text)
    if match is None:
        raise ValueError("missing QML object: " + header)
    start = text.find("{", match.start())
    if start < 0:
        raise ValueError("QML object has no body: " + header)
    depth = 0
    index = start
    quote = None
    line_comment = False
    while index < len(text):
        char = text[index]
        if line_comment:
            if char == "\n":
                line_comment = False
        elif quote is not None:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif char == "/" and text[index:index + 2] == "//":
            line_comment = True
            index += 1
        elif char in ("'", '"'):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
        index += 1
    raise ValueError("unclosed QML object: " + header)


def binding(block: str, name: str) -> str:
    """Return the expression assigned to a property in a QML object body."""
    pattern = re.compile(
        r"(?m)^[ \t]*(?:readonly[ \t]+)?"
        r"(?:property[ \t]+\w+[ \t]+)?" + re.escape(name) + r"[ \t]*:[ \t]*(.+?)[ \t]*$"
    )
    match = pattern.search(block)
    if match is None:
        raise ValueError("missing QML binding: " + name)
    return re.sub(r"[ \t]*//.*$", "", match.group(1)).strip()


def _has_clip(text: str) -> bool:
    return re.search(r"(?m)^[ \t]*clip:[ \t]*true\b", text) is not None


def load_sources(source_dir=None):
    """Read the three QML files the contracts depend on."""
    if source_dir is not None:
        _require_path(source_dir, "source_dir")
    base = Path(source_dir) if source_dir is not None else SOURCE
    return {
        "main": (base / "Main.qml").read_text(encoding="utf-8"),
        "theme": (base / "Theme.qml").read_text(encoding="utf-8"),
        "preview": (base / "PreviewWindow.qml").read_text(encoding="utf-8"),
    }


def screenshot_evidence(path, size) -> dict:
    """Validate an existing screenshot with the shared PNG checker and hash it."""
    _require_path(path, "screenshot path")
    _require_size(size, "screenshot size")
    check_screenshot.verify_png(Path(path), int(size[0]), int(size[1]))
    return {
        "name": Path(path).name,
        "size": [int(size[0]), int(size[1])],
        "sha256": file_sha256(path),
    }


def check_layout_contract(source_dir=None, *, size=None, sources=None,
                          screenshot=None) -> dict:
    """Check reduced-width reflow contracts against QML source.

    ``sources`` may supply {"main", "theme", "preview"} text directly, which
    lets callers test candidate edits without touching the real QML files.
    """
    width, height = _require_size(size, "size") if size is not None else REDUCED_SIZE
    text = sources if sources is not None else load_sources(source_dir)
    _require_sources(text)
    main, theme, preview = text["main"], text["theme"], text["preview"]

    min_width = int(binding(main, "minimumWidth"))
    min_height = int(binding(main, "minimumHeight"))
    compact_expr = binding(main, "compactLayout")
    compact_match = re.search(r"<\s*(\d+)", compact_expr)
    if compact_match is None:
        raise ValueError("compactLayout must compare width to a threshold")
    compact_threshold = int(compact_match.group(1))

    constants = {
        "canopyTheme." + name: float(binding(theme, name))
        for name in ("barHeight", "dockSize", "dockPadding")
    }
    scope = dict(constants)
    scope.update({"root.width": float(width), "root.height": float(height)})

    preview_body = object_block(main, r"PreviewWindow[ \t]*\{")
    preview_width = evaluate(binding(preview_body, "width"), scope)
    preview_height = evaluate(binding(preview_body, "height"), scope)
    scope["width"] = preview_width
    scope["height"] = preview_height
    preview_x = evaluate(binding(preview_body, "x"), scope)
    preview_y = evaluate(binding(preview_body, "y"), scope)

    dock_width_expr = re.search(
        r"id:[ \t]*dock\b[\s\S]{0,240}?width:[ \t]*([^\n]+)", main
    )
    if dock_width_expr is None:
        raise ValueError("missing dock width binding")
    scope["dockRow.implicitWidth"] = float(_LIMITER_VARIABLE)
    dock_width = evaluate(dock_width_expr.group(1), scope)

    preview_inside = (
        preview_x >= 0 and preview_y >= 0
        and preview_x + preview_width <= width
        and preview_y + preview_height <= height
    )
    contracts = {
        "above_minimum": width >= min_width and height >= min_height,
        "compact_layout_engages": width < compact_threshold,
        "preview_within_viewport": preview_inside,
        "dock_within_viewport": 0 <= dock_width <= width,
        "preview_clips_content": _has_clip(preview),
        "scrollers_clip_content": len(re.findall(
            r"(?m)^[ \t]*clip:[ \t]*true\b", preview
        )) >= 4,
        "overflow_scrolls": (
            "Flickable.StopAtBounds" in preview and "ScrollBar" in preview
        ),
        "long_labels_elide": "Text.ElideRight" in preview,
        "dock_clips_content": _has_clip(object_block(
            main, r"Rectangle[ \t]*\{[\s\S]{0,120}?id:[ \t]*dock\b"
        )),
    }
    failed = [name for name, passed in contracts.items() if not passed]

    return {
        "schema_version": 1,
        "size": f"{width}x{height}",
        "width": width,
        "height": height,
        "reduced_size_from_smoke_sizes": (width, height) == REDUCED_SIZE
                                         and REDUCED_SIZE in SIZES,
        "contracts": contracts,
        "geometry": {
            "minimum_width": min_width,
            "minimum_height": min_height,
            "compact_threshold": compact_threshold,
            "preview": {
                "x": preview_x, "y": preview_y,
                "width": preview_width, "height": preview_height,
                "right": preview_x + preview_width,
                "bottom": preview_y + preview_height,
            },
            "dock_width": dock_width,
        },
        "environment": {
            "host_os": os.name,
            "mode": "offline-source-contract",
            "compiled_qt_ran": False,
            "linux_mint_ran": False,
            "limitations": (
                "Static QML source analysis. No Qt binary, GUI, Mint guest, "
                "screenshot capture or pixel-level visual acceptance was run."
            ),
        },
        "screenshot": screenshot_evidence(screenshot, (width, height))
                      if screenshot is not None else None,
        "failed": failed,
        "status": "PASS" if not failed else "FAIL",
    }


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    size = REDUCED_SIZE
    if args:
        spec = args[0]
        if not isinstance(spec, str) or spec.count("x") != 1:
            raise ValueError("size argument must be WIDTHxHEIGHT")
        width, height = spec.split("x")
        size = (int(width), int(height))
    report = check_layout_contract(size=size)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
