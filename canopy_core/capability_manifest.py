"""Static, import-free audit of the pure capability catalog.

``verify`` checks every allowlisted capability target by locating its source
file under a source root and parsing that file with :mod:`ast`. It never
imports or executes a feature module, and no QML, C++, artwork or presentation
code is read. Malformed entries are reported as bounded problems rather than
raised, so the check can be used as a fail-closed offline CI gate.

This is metadata and path verification only: it is not an execution approval
or a runtime loader.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from canopy_core import capabilities

# Canonical problem reasons. Keep these stable: callers compare them as tokens.
EMPTY = "catalog empty"
INVALID = "invalid catalog entry"
MISSING = "module file missing"
NO_CALLABLE = "callable missing"
UNREADABLE = "module source unreadable"
UNSAFE = "unsafe module path"
VISUAL = "visual target rejected"

_VISUAL_MARKERS = frozenset({"qml", "visual", "presentation", "artwork", "wallpaper"})
_AREA = re.compile(r"^[a-z]+$")
_DEFAULT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ManifestProblem:
    """One bounded audit finding; ``name`` is empty only for catalog-level issues."""

    name: str
    reason: str


@dataclass(frozen=True)
class ManifestReport:
    """Immutable, deterministic result of one catalog audit."""

    checked: int
    ok: bool
    problems: tuple[ManifestProblem, ...]


def _entries_from_catalog():
    """Project the public catalog API into raw (module, attribute, area) tuples."""
    return {name: (described.module, described.attribute, described.area)
            for name in capabilities.names()
            for described in (capabilities.describe(name),)}


def _top_level_callables(tree: ast.Module) -> frozenset[str]:
    """Names bound at module top level to a def/class/lambda, without executing."""
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Lambda):
            if isinstance(node.target, ast.Name):
                found.add(node.target.id)
    return frozenset(found)


def _unsafe_components(root: Path, path: Path) -> bool:
    """Reject a symlinked root or any symlinked component below it."""
    if root.is_symlink():
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _entry_sort_key(name):
    """Total, non-raising order over arbitrary mapping keys.

    Valid string keys sort exactly as before. Non-string keys are grouped
    after them and ordered by their text and type name, so a malformed mapping
    can never abort the audit in ``sorted()`` before its INVALID problem is
    recorded. Both ``str()`` fallbacks are guarded for hostile objects.
    """
    if isinstance(name, str):
        # Bypass custom __lt__/__str__ on a str subclass.
        return (0, str.__str__(name), "")
    try:
        text = str(name)
    except Exception:
        text = ""
    return (1, text, type(name).__name__)


def verify(entries=None, root=None) -> ManifestReport:
    """Audit catalog targets as source text only; never import feature code.

    ``entries`` maps a capability name to ``(module, attribute, area)`` and
    defaults to the live static catalog. ``root`` defaults to the repository
    root. Both are injectable for offline tests; every injected value is held
    to the same regex validation as the owner-reviewed catalog. Malformed
    mapping keys are reported as bounded INVALID problems, never raised.
    """
    if entries is None:
        entries = _entries_from_catalog()
    if root is None:
        root = _DEFAULT_ROOT
    else:
        root = Path(root)

    problems = []
    for name in sorted(entries, key=_entry_sort_key):
        target = entries[name]
        if (not isinstance(name, str)
                or not capabilities.CAPABILITY_NAME.fullmatch(name)
                or not isinstance(target, tuple) or len(target) != 3
                or not all(isinstance(part, str) for part in target)):
            try:
                display = str(name)
            except Exception:
                display = ""
            problems.append(ManifestProblem(display, INVALID))
            continue
        module, attribute, area = target
        if (not capabilities.MODULE_NAME.fullmatch(module)
                or not capabilities.ATTRIBUTE_NAME.fullmatch(attribute)
                or not _AREA.fullmatch(area)):
            problems.append(ManifestProblem(name, INVALID))
            continue

        looks_visual = any(marker in part
                           for part in module.split(".")
                           for marker in _VISUAL_MARKERS)
        if name in capabilities.names() and capabilities.describe(name).visual:
            looks_visual = True
        if looks_visual:
            problems.append(ManifestProblem(name, VISUAL))
            continue

        path = root.joinpath(*module.split(".")).with_suffix(".py")
        if _unsafe_components(root, path):
            problems.append(ManifestProblem(name, UNSAFE))
            continue
        if not path.is_file():
            problems.append(ManifestProblem(name, MISSING))
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, ValueError, SyntaxError, RecursionError):
            problems.append(ManifestProblem(name, UNREADABLE))
            continue
        if attribute not in _top_level_callables(tree):
            problems.append(ManifestProblem(name, NO_CALLABLE))

    ordered = tuple(sorted(problems, key=lambda problem: (problem.name, problem.reason)))
    if not entries:
        ordered = (ManifestProblem("", EMPTY),) + ordered
    return ManifestReport(checked=len(entries), ok=bool(entries) and not ordered,
                          problems=ordered)


def main(argv=None) -> int:
    """Offline CLI: exit 0 when the audited catalog is clean, else 1."""
    args = sys.argv[1:] if argv is None else list(argv)
    root = Path(args[0]) if args else _DEFAULT_ROOT
    report = verify(root=root)
    if report.ok:
        print("CAPABILITY_MANIFEST_OK checked=" + str(report.checked))
        return 0
    print("CAPABILITY_MANIFEST_FAIL checked=" + str(report.checked)
          + " problems=" + str(len(report.problems)))
    for problem in report.problems:
        print((problem.name or "<catalog>") + ": " + problem.reason)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
