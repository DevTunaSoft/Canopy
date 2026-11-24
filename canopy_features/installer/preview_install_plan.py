"""Dry-run installation planner for the Canopy Classic preview on Linux Mint.

Produces a deterministic, JSON-serializable plan describing the exact steps a
reversible, unprivileged install would perform. This module never installs,
launches the Qt binary, changes a session, uses root or contacts a network.
It reuses the real tools' paths, constants and validation so the plan stays in
sync with the capabilities it describes.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys

from tools import mint_classic_qt_smoke as smoke
from tools import mint_guest_preflight as preflight
from tools import register_classic_preview as menu

PLAN_SCHEMA_VERSION = 1
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
TOKEN = re.compile(r"[A-Za-z0-9._+:-]{1,40}\Z")


class PlanError(ValueError):
    """Input or output failed a safety gate before any plan was produced."""


def _path_arg(value, name):
    """Coerce a caller-supplied path to text, failing closed on wrong types.

    ``Path(value)`` and ``os.fspath(value)`` leak a raw ``TypeError`` for
    non-path values and for PathLike objects with a hostile ``__fspath__``.
    Every path boundary in this module translates those into ``PlanError`` so
    an offline plan never exits on a built-in exception.
    """
    if not isinstance(value, (str, os.PathLike)):
        raise PlanError(name + " must be a path string or PathLike")
    try:
        text = os.fspath(value)
    except Exception as exc:
        raise PlanError(name + " must be a readable path string") from exc
    if not isinstance(text, str):
        raise PlanError(name + " must be a path string or PathLike")
    return text


def validate_qt_binary(binary):
    """Return the absolute path of a safe, executable Qt binary.

    Uses os.access for the execute bit because Windows has no POSIX mode bits;
    the existing smoke helper uses st_mode and rejects ordinary Windows files.
    """
    path = Path(_path_arg(binary, "Qt executable"))
    if not path.is_absolute():
        raise PlanError("Qt executable must be an absolute path")
    if smoke._has_symlink_component(path):
        raise PlanError("Qt executable must not contain symlink components")
    if not path.is_file():
        raise PlanError("Qt executable is missing or not a regular file")
    if not os.access(str(path), os.X_OK):
        raise PlanError("Qt executable is not executable")
    return str(path)


def _optional_resource(value, name, *, directory=False):
    """Validate an optional install resource with the real installer's rule."""
    if value is None:
        return None
    try:
        return menu._resource(value, name, directory=directory)
    except menu.RegistrationError as exc:
        raise PlanError(str(exc)) from exc


def _token(value, name):
    if value is None:
        return None
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise PlanError(name + " must be a short plain token")
    return value


def _source_sha(value):
    if value is None:
        return None
    if not isinstance(value, str) or not SHA40.fullmatch(value):
        raise PlanError("source_sha must be a 40-character lowercase SHA")
    return value


def build_plan(qt_binary, *, data_home=None, art=None, wallpaper=None,
               terminal=None, native_apps=False, mint_release=None,
               session_type=None, source_sha=None):
    """Build a bounded, offline plan. No filesystem changes or execution."""
    binary = validate_qt_binary(qt_binary)
    art = _optional_resource(art, "approved artwork", directory=True)
    wallpaper = _optional_resource(wallpaper, "approved wallpaper")
    terminal = _optional_resource(terminal, "Terminal candidate")
    if terminal and not art:
        raise PlanError("Terminal candidate requires approved artwork")
    release = _token(mint_release, "mint_release")
    session = _token(session_type, "session_type")
    digest = _source_sha(source_sha)

    home = (Path(_path_arg(data_home, "data_home"))
            if data_home is not None else menu.data_home())
    if not home.is_absolute():
        raise PlanError("data_home must be an absolute path")
    destinations = menu.paths(home)

    menu_command = ["python3", "tools/register_classic_preview.py", "install",
                    "--binary", binary]
    for flag, value in (("--approved-art-dir", art),
                        ("--landscape-wallpaper", wallpaper),
                        ("--terminal-refinement", terminal)):
        if value:
            menu_command.extend((flag, value))
    if native_apps:
        menu_command.append("--enable-system-apps")

    smoke_missing = [name for name, present in (
        ("approved artwork", art), ("approved wallpaper", wallpaper),
        ("source_sha", digest)) if not present]
    smoke_command = [
        "python3", "tools/mint_classic_qt_smoke.py",
        "--binary", binary,
        "--approved-art-dir", art or "<approved-art>",
        "--landscape-wallpaper", wallpaper or "<wallpaper>",
        "--output-dir", "<new absolute evidence directory>",
        "--source-sha", digest or "<40-character source SHA>",
    ]
    if terminal:
        smoke_command.extend(("--terminal-refinement", terminal))

    steps = [
        {
            "phase": "preflight",
            "description": "Read-only Linux Mint/Cinnamon readiness probe.",
            "tool": "tools/mint_guest_preflight.py",
            "command": ["python3", "tools/mint_guest_preflight.py", "--json"],
            "required_tools": list(preflight.NEEDED),
            "status": "DESCRIBED_NOT_RUN",
        },
        {
            "phase": "verify-binary",
            "description": "Confirm compiled Qt binary is absolute, real and "
                           "executable.",
            "path": binary,
            "checked": ["absolute", "no_symlink_components", "regular_file",
                        "executable"],
            "status": "OK",
        },
        {
            "phase": "install",
            "description": "Add a reversible per-user menu entry; no root, "
                           "session or display-manager change.",
            "tool": "tools/register_classic_preview.py",
            "command": menu_command,
            "writes": [str(destinations["desktop"]),
                       str(destinations["manifest"])],
            "owned_by": menu.DESKTOP,
            "privileged": False,
            "status": "READY",
        },
        {
            "phase": "smoke",
            "description": "Capture real Qt screenshots inside a Mint guest; "
                           "changes no system setting.",
            "tool": "tools/mint_classic_qt_smoke.py",
            "command": smoke_command,
            "resolutions": [f"{w}x{h}" for w, h in smoke.SIZES],
            "required_markers": list(smoke.REQUIRED_MARKERS),
            "status": "BLOCKED" if smoke_missing else "READY",
            "missing": smoke_missing,
        },
        {
            "phase": "rollback",
            "description": "Remove only the exact owned entry and marker; "
                           "refuse to delete modified files.",
            "tool": "tools/register_classic_preview.py",
            "command": ["python3", "tools/register_classic_preview.py",
                        "uninstall"],
            "status": "READY",
        },
    ]
    if digest is not None:
        steps.insert(2, {
            "phase": "record-source",
            "description": "Pin the exact source revision used to build the "
                           "preview binary.",
            "source_sha256": digest,
            "status": "RECORDED",
        })
    for order, step in enumerate(steps, 1):
        step["order"] = order

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "dry_run": True,
        "performs_install": False,
        "privileged": False,
        "target": "Linux Mint with Cinnamon (preview application only)",
        "mint_release": release,
        "session_type": session,
        "source_sha256": digest,
        "qt_binary": binary,
        "data_home": str(home),
        "destinations": {key: str(value) for key, value in destinations.items()},
        "optional_resources": {
            "approved_art": art,
            "approved_wallpaper": wallpaper,
            "terminal_refinement": terminal,
            "native_apps": bool(native_apps),
        },
        "reused_capabilities": [
            "tools.register_classic_preview.paths/_resource/DESKTOP/data_home",
            "tools.mint_guest_preflight.NEEDED",
            "tools.mint_classic_qt_smoke.SIZES/REQUIRED_MARKERS",
        ],
        "steps": steps,
        "not_proven": [
            "No Linux Mint guest was contacted; the target is a description.",
            "No compiled Qt application was built, launched or screenshotted.",
            "This plan does not prove visual, session or accessibility "
            "acceptance.",
        ],
    }


def authorize_output(output_path, *, allowed_root=None):
    """Return a new, writable .json path inside an authorized root."""
    path = Path(_path_arg(output_path, "plan output"))
    if not path.is_absolute() or path.suffix != ".json":
        raise PlanError("plan output must be an absolute .json path")
    if smoke._has_symlink_component(path):
        raise PlanError("plan output must not contain symlink components")
    root = (Path(_path_arg(allowed_root, "allowed root"))
            if allowed_root is not None else Path.cwd())
    if not root.is_absolute():
        raise PlanError("allowed root must be an absolute path")
    root = root.resolve()
    try:
        inside = path.resolve().relative_to(root)
    except ValueError:
        raise PlanError("plan output is outside the authorized root") from None
    if str(inside) in ("", "."):
        raise PlanError("plan output must be a file inside the authorized root")
    if path.exists():
        raise PlanError("plan output already exists; refusing to overwrite")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise PlanError("plan output parent must be a real existing directory")
    return path


def write_plan(plan, output_path, *, allowed_root=None):
    """Serialize a plan with exclusive creation; return the written path."""
    path = authorize_output(output_path, allowed_root=allowed_root)
    text = json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def main(argv=None):
    """CLI: build and write a plan; never install or execute the binary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--data-home", type=Path)
    parser.add_argument("--approved-art-dir", type=Path)
    parser.add_argument("--landscape-wallpaper", type=Path)
    parser.add_argument("--terminal-refinement", type=Path)
    parser.add_argument("--enable-system-apps", action="store_true")
    parser.add_argument("--mint-release")
    parser.add_argument("--session-type")
    parser.add_argument("--source-sha")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allowed-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = build_plan(
            args.binary, data_home=args.data_home,
            art=args.approved_art_dir, wallpaper=args.landscape_wallpaper,
            terminal=args.terminal_refinement,
            native_apps=args.enable_system_apps,
            mint_release=args.mint_release, session_type=args.session_type,
            source_sha=args.source_sha,
        )
        written = write_plan(result, args.output,
                             allowed_root=args.allowed_root)
    except PlanError as exc:
        print("CANOPY_PREVIEW_PLAN_FAIL:", exc, file=sys.stderr)
        return 1
    print("CANOPY_PREVIEW_PLAN:", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
