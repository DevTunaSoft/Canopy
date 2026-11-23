"""Offline resize/reflow contract evidence for the Classic Qt QML layout.

Reads the existing prototype QML bindings, evaluates the small numeric subset
they use at a given window size, and reports clipped content or overflow.
No Qt process, X server, network, timers, services or polling are involved.

This is a static contract check, not a Qt render. Text line height is
estimated as font pixel size plus TEXT_LINE_PAD; see README/QUALITY docs for
the runtime screenshot gates that complement this check.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
import json
import operator
from pathlib import Path
import re
import sys

DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "prototype" / "classic"
DEFAULT_SIZE = (760, 500)
# main.cpp self-test allows 720x480 through 3840x2160.
MIN_SIZE = (720, 480)
# main.cpp: contentHeight <= scroller height + 3; chrome edges allow 1 px.
SCROLL_TOLERANCE = 3
EDGE_TOLERANCE = 1
DOCK_CLEARANCE = 12
# Estimate only: Qt Quick label implicit height is not expressed in QML.
TEXT_LINE_PAD = 4

_QML_FILES = ("Main.qml", "Theme.qml", "PreviewWindow.qml",
              "FolderTile.qml", "DockTile.qml", "LauncherOverlay.qml")
_PROP = re.compile(r"^(?:(?:readonly\s+)?property\s+\w+\s+)?([A-Za-z_][\w.]*)\s*:\s*(.*)$")
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMPOPS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}


class ContractError(ValueError):
    """Required QML source, binding or expression is absent or unsupported."""


@dataclass(frozen=True)
class Finding:
    code: str
    item: str
    detail: str

    def as_dict(self) -> dict:
        return {"code": self.code, "item": self.item, "detail": self.detail}


@dataclass(frozen=True)
class ReflowReport:
    size: tuple[int, int]
    metrics: dict = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {"size": list(self.size), "ok": self.ok,
                "metrics": dict(self.metrics),
                "findings": [f.as_dict() for f in self.findings]}


def _strip_line_comment(line: str) -> str:
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "/" and line[index:index + 2] == "//":
            return line[:index]
    return line


def _delta(text: str) -> int:
    text = re.sub(r"\"[^\"]*\"|'[^']*'", "", text)
    return sum(text.count(opening) for opening in "([{") - sum(
        text.count(closing) for closing in ")]}")


def _scan_block(source: str, opening: int) -> str:
    """Return the body starting at an opening brace, ignoring QML literals."""
    depth = 0
    quote = None
    index = opening
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif source.startswith("//", index):
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline
            continue
        elif source.startswith("/*", index):
            close = source.find("*/", index + 2)
            index = len(source) if close < 0 else close + 2
            continue
        elif char in "\"'":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
        index += 1
    raise ContractError("unbalanced QML braces")


def object_block(source: str, anchor: str) -> str:
    """Return the brace-delimited body of the object containing anchor."""
    position = source.find(anchor)
    if position < 0:
        raise ContractError("missing QML anchor: " + anchor)
    opening = source.rfind("{", 0, position)
    if opening < 0:
        raise ContractError("no enclosing object for anchor: " + anchor)
    return _scan_block(source, opening)


def root_block(source: str, header: str) -> str:
    """Return the body of a file-level object such as ``QtObject {``."""
    match = re.search(r"\b" + re.escape(header) + r"\s*\{", source)
    if not match:
        raise ContractError("missing QML root object: " + header)
    return _scan_block(source, source.index("{", match.start()))


def bindings(block: str) -> dict[str, str]:
    """Map direct property bindings of one QML object body to expressions."""
    lines = [_strip_line_comment(line).strip() for line in block.splitlines()]
    lines = [line for line in lines if line]
    result: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = _PROP.match(lines[index])
        if not match:
            # Child objects and functions are not bindings of this object.
            depth = _delta(lines[index])
            index += 1
            while depth > 0 and index < len(lines):
                depth += _delta(lines[index])
                index += 1
            continue
        name, parts = match.group(1), [match.group(2).strip()]
        depth = _delta(match.group(2))
        index += 1
        while index < len(lines):
            following = lines[index]
            if depth <= 0:
                if _PROP.match(following) or following.startswith("}"):
                    break
                if following[0] not in "?:+-*/&|.),":
                    break
            parts.append(following)
            depth += _delta(following)
            index += 1
        result[name] = " ".join(parts).strip()
    return result


def _find_token(text: str, token: str, start: int = 0,
                target_depth: int | None = None) -> tuple[int, int] | None:
    """Find a token outside string literals, optionally at a fixed depth."""
    depth = 0
    quote = None
    index = start
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif (target_depth is None or depth == target_depth) and text.startswith(
                token, index):
            return index, depth
        index += 1
    return None


def _condition_bounds(text: str, question: int, colon: int) -> tuple[int, int]:
    """Find the full span of a ?: expression without eating enclosing code."""
    depth = 0
    start = 0
    for index in range(question - 1, -1, -1):
        char = text[index]
        if char in ")]}":
            depth += 1
        elif char in "([{":
            if depth == 0:
                start = index + 1
                break
            depth -= 1
        elif depth == 0 and char in "?:,=":
            start = index + 1
            break
    depth = 0
    end = len(text)
    for index in range(colon + 1, len(text)):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                end = index
                break
            depth -= 1
        elif depth == 0 and char in ",;":
            end = index
            break
    return start, end


def _conditionals(text: str) -> str:
    """Translate QML a ? b : c in place into a Python conditional expression."""
    found = _find_token(text, "?")
    if found is None:
        return text
    question, _ = found
    colon_match = _find_token(text, ":", question + 1, 0)
    if colon_match is None:
        raise ContractError("unbalanced QML conditional: " + text)
    colon = colon_match[0]
    start, end = _condition_bounds(text, question, colon)
    replacement = "({}) if ({}) else ({})".format(
        _conditionals(text[question + 1:colon].strip()),
        _conditionals(text[start:question].strip()),
        _conditionals(text[colon + 1:end].strip()))
    return text[:start] + replacement + text[end:]


def _to_python(expression: str) -> str:
    text = _conditionals(expression.strip())
    text = text.replace("Math.min", "_min").replace("Math.max", "_max")
    text = text.replace("===", "==").replace("!==", "!=")
    text = text.replace("&&", " and ").replace("||", " or ")
    text = re.sub(r"(?<![!=])!(?!=)", " not ", text)
    text = re.sub(r"\btrue\b", "True", text)
    text = re.sub(r"\bfalse\b", "False", text)
    keywords = {"and", "or", "not", "if", "else", "True", "False",
                "_min", "_max", "_lookup"}

    def name(match: re.Match) -> str:
        value = match.group(0)
        if value in keywords or value.startswith("_"):
            return value
        return "_lookup({!r})".format(value)

    # Replace names once, outside string literals, so generated lookups are
    # never re-read as QML names.
    pieces = re.split(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')", text)
    return "".join(part if index % 2 else re.sub(
        r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\b", name, part)
        for index, part in enumerate(pieces))


def evaluate(expression: str, context: dict) -> object:
    """Evaluate a numeric/bool QML binding; reject anything outside the subset."""
    try:
        tree = ast.parse(_to_python(expression), mode="eval")
    except SyntaxError as exc:
        raise ContractError("unsupported QML expression: " + expression) from exc

    def visit(node: ast.AST) -> object:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(
                node.value, (int, float, bool, str)):
            return node.value
        if isinstance(node, ast.Name) and node.id == "_lookup":
            return _lookup  # only reached as a Call func below
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "_lookup" and len(node.args) == 1:
                return _lookup(visit(node.args[0]), context)
            if node.func.id in ("_min", "_max") and len(node.args) >= 2:
                values = [visit(arg) for arg in node.args]
                return (min if node.func.id == "_min" else max)(values)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            right = visit(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ContractError("division by zero: " + expression)
            return _BINOPS[type(node.op)](visit(node.left), right)
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return +value
            if isinstance(node.op, ast.Not):
                return not value
        if isinstance(node, ast.BoolOp):
            values = [visit(value) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = visit(comparator)
                if type(op) not in _CMPOPS or not _CMPOPS[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return visit(node.body) if visit(node.test) else visit(node.orelse)
        raise ContractError("unsupported QML expression: " + expression)

    return visit(tree)


def _lookup(name: str, context: dict) -> object:
    if name not in context:
        raise ContractError("unbound QML name: " + name)
    return context[name]


def _need(source: dict, name: str, where: str) -> str:
    if name not in source:
        raise ContractError("missing binding {}.{}".format(where, name))
    return source[name]


def _number(value: object, expression: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("expected number from: " + expression)
    return float(value)


def check_layout(source_dir: Path = DEFAULT_SOURCE,
                 width: int = DEFAULT_SIZE[0],
                 height: int = DEFAULT_SIZE[1]) -> ReflowReport:
    """Check resize/reflow contracts of real Classic QML at WIDTH x HEIGHT."""
    source_dir = Path(source_dir)
    text = {}
    for name in _QML_FILES:
        path = source_dir / name
        if not path.is_file():
            raise ContractError("missing QML source: " + str(path))
        text[name] = path.read_text(encoding="utf-8")

    findings: list[Finding] = []
    metrics: dict[str, object] = {"window_width": width, "window_height": height}
    if width < MIN_SIZE[0] or height < MIN_SIZE[1]:
        findings.append(Finding("minimum-size", "window",
                                "{}x{} is below the {}x{} QML minimum".format(
                                    width, height, *MIN_SIZE)))

    theme = bindings(root_block(text["Theme.qml"], "QtObject"))
    main_root = bindings(object_block(text["Main.qml"], "id: root"))
    context = {
        "root.width": float(width), "root.height": float(height),
        "parent.width": float(width), "parent.height": float(height),
        "width": float(width), "height": float(height),
    }
    for key in ("barHeight", "dockSize", "dockPadding", "dockSpacing"):
        context["canopyTheme." + key] = _number(
            evaluate(_need(theme, key, "Theme"), context), "Theme." + key)

    compact = bool(evaluate(_need(main_root, "compactLayout", "Main"), context))
    context["root.compactLayout"] = compact
    metrics["compact_layout"] = compact

    preview_block = bindings(object_block(text["Main.qml"], "id: filesPreview"))
    preview_width = _number(evaluate(
        _need(preview_block, "width", "filesPreview"), context), "preview width")
    context["width"] = preview_width
    preview_height = _number(evaluate(
        _need(preview_block, "height", "filesPreview"), context), "preview height")
    context["height"] = preview_height
    preview_x = _number(evaluate(
        _need(preview_block, "x", "filesPreview"), context), "preview x")
    preview_y = _number(evaluate(
        _need(preview_block, "y", "filesPreview"), context), "preview y")
    metrics.update(preview_x=preview_x, preview_y=preview_y,
                   preview_width=preview_width, preview_height=preview_height)

    dock_block = bindings(object_block(text["Main.qml"], 'objectName: "canopyDock"'))
    dock_row = bindings(object_block(text["Main.qml"], "id: dockRow"))
    repeater = bindings(object_block(text["Main.qml"], "model: canopyApprovedMode"))
    first_array = re.search(r"\[(.*?)\]", _need(repeater, "model", "Repeater"), re.S)
    if not first_array:
        raise ContractError("missing approved dock model array")
    tile_count = len(re.findall(r"title:\s*\"", first_array.group(1)))
    tile = bindings(object_block(text["DockTile.qml"], "id: tile"))
    tile_width = _number(evaluate(_need(tile, "width", "DockTile"), {}), "tile width")
    row_width = (tile_count * tile_width +
                 (tile_count - 1) * context["canopyTheme.dockSpacing"])
    context["dockRow.implicitWidth"] = row_width
    dock_width = _number(evaluate(_need(dock_block, "width", "dock"), context),
                         "dock width")
    dock_height = context["canopyTheme.dockSize"]
    dock_x = (width - dock_width) / 2
    dock_bottom_margin = _number(evaluate(
        _need(dock_block, "anchors.bottomMargin", "dock"), context),
        "dock bottom margin")
    dock_y = height - dock_height - dock_bottom_margin
    metrics.update(dock_x=dock_x, dock_y=dock_y,
                   dock_width=dock_width, dock_height=dock_height,
                   dock_tile_count=tile_count, dock_row_width=row_width)

    panel_block = bindings(object_block(text["LauncherOverlay.qml"], "id: panel"))
    panel_width = _number(evaluate(_need(panel_block, "width", "panel"), context),
                          "launcher panel width")
    panel_height = _number(evaluate(_need(panel_block, "height", "panel"), context),
                           "launcher panel height")
    metrics.update(panel_width=panel_width, panel_height=panel_height)

    def overflow(item: str, x: float, y: float, item_width: float,
                 item_height: float, extra_bottom: float = 0.0) -> None:
        right = x + item_width
        bottom = y + item_height + extra_bottom
        if (x < -EDGE_TOLERANCE or y < -EDGE_TOLERANCE or
                right > width + EDGE_TOLERANCE or
                bottom > height + EDGE_TOLERANCE):
            findings.append(Finding(
                "overflow", item,
                "bounds ({:.1f},{:.1f}) {:.1f}x{:.1f} exceed {}x{}".format(
                    x, y, item_width, item_height + extra_bottom, width, height)))

    overflow("filesPreview", preview_x, preview_y, preview_width, preview_height)
    overflow("dock", dock_x, dock_y, dock_width, dock_height)
    overflow("launcherPanel", (width - panel_width) / 2,
             (height - panel_height) / 2, panel_width, panel_height)
    if preview_y + preview_height > dock_y - DOCK_CLEARANCE:
        findings.append(Finding(
            "chrome-overlap", "filesPreview",
            "preview bottom {:.1f} reaches dock top {:.1f}".format(
                preview_y + preview_height, dock_y)))

    preview_window = bindings(object_block(text["PreviewWindow.qml"], "id: preview"))
    context["preview.condensed"] = bool(evaluate(
        _need(preview_window, "condensed", "PreviewWindow"), context))
    context["preview.width"] = preview_width
    metrics["condensed"] = context["preview.condensed"]

    def block_binding(source: str, anchor: str, name: str, where: str) -> str:
        return _need(bindings(object_block(text[source], anchor)), name, where)

    titlebar_height = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: titlebar", "height", "titlebar"),
        context), "titlebar height")
    statusbar_height = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: statusBar", "height", "statusBar"),
        context), "statusBar height")
    toolbar_height = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: toolbar", "height", "toolbar"),
        context), "toolbar height")
    sidebar_width = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: sidebar", "width", "sidebar"),
        context), "sidebar width")

    heading_left = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: heading", "anchors.leftMargin",
                      "heading"), context), "heading left margin")
    heading_top = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: heading", "anchors.topMargin",
                      "heading"), context), "heading top margin")
    subtitle_gap = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: subtitle", "anchors.topMargin",
                      "subtitle"), context), "subtitle top margin")
    heading_font = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: heading", "font.pixelSize",
                      "heading"), context), "heading font")
    subtitle_font = _number(evaluate(
        block_binding("PreviewWindow.qml", "id: subtitle", "font.pixelSize",
                      "subtitle"), context), "subtitle font")

    scroller_block = bindings(object_block(text["PreviewWindow.qml"],
                                           "id: folderScroller"))
    scroller_top = _number(evaluate(
        _need(scroller_block, "anchors.topMargin", "folderScroller"), context),
        "scroller top margin")
    scroller_right = _number(evaluate(
        _need(scroller_block, "anchors.rightMargin", "folderScroller"), context),
        "scroller right margin")
    scroller_bottom = _number(evaluate(
        _need(scroller_block, "anchors.bottomMargin", "folderScroller"), context),
        "scroller bottom margin")

    content_width = preview_width - sidebar_width
    content_height = preview_height - titlebar_height - toolbar_height - statusbar_height
    scroller_width = content_width - heading_left - scroller_right
    text_stack = (heading_top + heading_font + TEXT_LINE_PAD + subtitle_gap +
                  subtitle_font + TEXT_LINE_PAD)
    scroller_height = content_height - text_stack - scroller_top - scroller_bottom

    folders_block = bindings(object_block(text["PreviewWindow.qml"], "id: folders"))
    folder_width_expression = _need(folders_block, "width", "folders")
    folder_spacing = _number(evaluate(
        _need(folders_block, "spacing", "folders"), context), "folder spacing")
    folder_tile = bindings(object_block(text["FolderTile.qml"], "id: folder"))
    folder_tile_width = _number(evaluate(
        _need(folder_tile, "width", "FolderTile"), context), "folder tile width")
    columns_match = re.search(r"(\d+)\s*\*\s*{:g}".format(folder_tile_width),
                              folder_width_expression)
    if not columns_match:
        raise ContractError("cannot read folder column cap from QML")
    columns = int(columns_match.group(1))
    sample_match = re.search(r"sampleFolders:\s*\[(.*?)\]",
                             text["PreviewWindow.qml"], re.S)
    if not sample_match:
        raise ContractError("missing sampleFolders model")
    folder_count = len(re.findall(r"name:\s*\"", sample_match.group(1)))
    rows = (folder_count + columns - 1) // columns
    # PreviewWindow.qml passes preview.condensed into FolderTile.compact.
    context["compact"] = context["preview.condensed"]
    folder_tile_height = _number(evaluate(
        _need(folder_tile, "height", "FolderTile"), context), "folder tile height")
    folder_grid_height = rows * folder_tile_height + (rows - 1) * folder_spacing

    context["folderScroller.width"] = scroller_width
    context["folders.height"] = folder_grid_height
    flow_width = _number(evaluate(folder_width_expression, context), "folder flow width")
    context["height"] = scroller_height
    content_height_binding = _need(scroller_block, "contentHeight", "folderScroller")
    scroll_content = _number(evaluate(content_height_binding, context),
                             "folder scroller contentHeight")
    if scroll_content > scroller_height + SCROLL_TOLERANCE:
        findings.append(Finding(
            "clipped-content", "folderScroller",
            "content height {:.1f} exceeds viewport {:.1f} by {:.1f}px".format(
                scroll_content, scroller_height,
                scroll_content - scroller_height)))
    if not 449.5 <= flow_width <= 462.5:
        findings.append(Finding(
            "grid-cap", "folderFlow",
            "width {:.1f} outside four-column cap 449.5..462.5".format(flow_width)))

    metrics.update(folder_columns=columns, folder_rows=rows,
                   folder_grid_height=folder_grid_height,
                   folder_scroller_width=scroller_width,
                   folder_scroller_height=scroller_height,
                   folder_flow_width=flow_width,
                   folder_content_height=scroll_content)
    return ReflowReport((width, height), metrics, tuple(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("size", nargs="?", default="{}x{}".format(*DEFAULT_SIZE),
                        help="WIDTHxHEIGHT (default: 760x500)")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="directory containing the Classic QML sources")
    args = parser.parse_args(argv)
    match = re.fullmatch(r"(\d+)x(\d+)", args.size)
    if not match:
        parser.error("size must be WIDTHxHEIGHT")
    width, height = int(match.group(1)), int(match.group(2))
    try:
        report = check_layout(args.source, width, height)
    except ContractError as exc:
        print(json.dumps({"size": [width, height], "ok": False,
                          "findings": [{"code": "contract", "item": "source",
                                        "detail": str(exc)}]}, indent=2))
        return 2
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
