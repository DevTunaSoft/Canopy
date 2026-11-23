"""Dry-run Linux Mint preview installation planner.

Build a deterministic, side-effect-free plan describing exactly what the
existing per-user Classic preview installer (``tools/register_classic_preview``)
would create on this host. The planner reuses that installer's path, quoting
and payload logic so the plan cannot silently drift from a real install.

It never writes to the install target, never runs the Qt binary, never launches
an app and never changes the desktop session. A plan is reviewable evidence,
not acceptance: it does not prove Linux Mint guest behaviour, compiled Qt
execution, visual approval or a working desktop.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from tools import mint_guest_preflight as preflight
from tools import register_classic_preview as register


class PlanError(ValueError):
    """An output destination is not authorized or is unsafe."""


def _has_symlink_component(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _validate_binary(binary):
    """Return ``(absolute path or None, error message or None)``."""
    try:
        candidate = Path(os.path.abspath(os.fspath(binary)))
    except (TypeError, ValueError) as exc:
        return None, str(exc)
    # register._resource requires an absolute, existing, non-symlink file.
    try:
        exe = register._resource(candidate, "Canopy Qt executable")
    except (register.RegistrationError, ValueError, TypeError) as exc:
        return None, str(exc)
    if not os.access(exe, os.X_OK):
        return exe, "Canopy Qt executable is not executable"
    return exe, None


def _exec_args(exe, art, wallpaper, terminal, native_apps):
    """Mirror register_classic_preview.install's argv construction exactly."""
    args = [exe]
    for flag, value in (
        ("--approved-art-dir", art),
        ("--landscape-wallpaper", wallpaper),
        ("--terminal-refinement", terminal),
    ):
        if value:
            args.extend((flag, value))
    if native_apps:
        args.append("--enable-system-apps")
    return args


def build_plan(binary, *, art=None, wallpaper=None, terminal=None,
               native_apps=False, home=None, preflight_report=None):
    """Return a dry-run plan dict. Never writes files or launches processes."""
    blockers = []
    warnings = []

    home = home if home is not None else register.data_home()
    paths = register.paths(home)
    targets = {
        "data_home": str(paths["data"]),
        "preview_dir": str(paths["folder"]),
        "applications_dir": str(paths["apps"]),
        "desktop_entry": str(paths["desktop"]),
        "ownership_manifest": str(paths["manifest"]),
    }

    # Authorization: no root/system-wide install and no unsafe target tree.
    try:
        register._unprivileged()
    except register.RegistrationError as exc:
        blockers.append(str(exc))
    try:
        register._safe_folders(paths)
    except register.RegistrationError as exc:
        blockers.append(str(exc))

    exe, binary_error = _validate_binary(binary)
    if binary_error:
        blockers.append(binary_error)

    resources = {}
    for name, value, directory in (
        ("approved artwork", art, True),
        ("landscape wallpaper", wallpaper, False),
        ("Terminal candidate", terminal, False),
    ):
        if value is None:
            resources[name] = None
            continue
        try:
            resources[name] = register._resource(value, name, directory=directory)
        except (register.RegistrationError, ValueError, TypeError) as exc:
            resources[name] = None
            blockers.append(str(exc))

    if preflight_report is None:
        preflight_report = preflight.collect()
    if (not isinstance(preflight_report, dict)
            or preflight_report.get("status") != "READY_FOR_TESTS"):
        warnings.append(
            "Linux Mint preflight not ready; no guest, Qt or visual test was run"
        )

    exec_argv = exec_command = desktop_payload = manifest_payload = None
    if exe is not None and not binary_error:
        art_value = resources["approved artwork"]
        wallpaper_value = resources["landscape wallpaper"]
        terminal_value = resources["Terminal candidate"]
        if terminal_value and not art_value:
            blockers.append("Terminal candidate requires approved art")
        else:
            exec_argv = _exec_args(
                exe, art_value, wallpaper_value, terminal_value, native_apps
            )
            # A Linux Mint desktop Exec uses POSIX paths. On a Windows host
            # Path.as_posix() removes backslashes that _quote correctly bans.
            posix_args = [Path(arg).as_posix() for arg in exec_argv]
            try:
                exec_command = " ".join(register._quote(arg) for arg in posix_args)
            except register.RegistrationError as exc:
                blockers.append(str(exc))
            if exec_command is not None:
                # Keep this byte-for-byte identical to register_classic_preview.install.
                desktop_payload = (
                    "[Desktop Entry]\nType=Application\nVersion=1.0\n"
                    "Name=Canopy Classic Preview\n"
                    "Comment=Experimental application, "
                    "not a replacement Cinnamon session\n"
                    "Exec=" + exec_command + "\n"
                    "Terminal=false\nIcon=computer\nCategories=Utility;\n"
                    "StartupNotify=false\nX-Canopy-Preview=true\n"
                )
                digest = hashlib.sha256(
                    desktop_payload.encode("utf-8")
                ).hexdigest()
                manifest_payload = json.dumps(
                    {"schema": 1, "sha256": digest}, sort_keys=True
                )

    actions = [
        "validate absolute, non-symlink Qt binary and optional resources",
        "create data home, canopy preview folder and applications folder (0700)",
        "write " + paths["desktop"].name + " desktop entry (0644, O_EXCL)",
        "write " + paths["manifest"].name + " ownership marker (0600, O_EXCL)",
        "user may uninstall later via exact-byte ownership check",
    ]

    return {
        "schema_version": 1,
        "tool": "canopy_features.installer.preview_install_plan",
        "dry_run": True,
        "status": "BLOCKED" if blockers else "READY",
        "target": targets,
        "exec_program": exe,
        "exec_argv": exec_argv,
        "exec_command": exec_command,
        "desktop_entry_payload": desktop_payload,
        "ownership_manifest_payload": manifest_payload,
        "planned_actions": actions,
        "preflight": preflight_report,
        "blockers": blockers,
        "warnings": warnings,
        "not_proven": [
            "linux_mint_guest_acceptance",
            "compiled_qt_execution",
            "visual_owner_approval",
            "working_desktop_session",
            "same_session_shell_pack_switching",
        ],
        "integration_note": (
            "Dry-run plan only: no files written, no Qt launched, no session "
            "changed. This modular component does not prove a working desktop "
            "until wired into the compiled Qt application and exercised on "
            "real Linux Mint."
        ),
    }


def render_json(plan):
    """Serialize a plan to stable JSON text. Writes nothing."""
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def write_plan(plan, path, *, allowed_root=None):
    """Write plan JSON only to an authorized, new file under ``allowed_root``.

    Refuses root privilege, relative paths, symlinked components, paths outside
    the authorized root and existing files. Never overwrites.
    """
    try:
        register._unprivileged()
    except register.RegistrationError as exc:
        raise PlanError(str(exc)) from exc
    target = Path(path)
    if not target.is_absolute():
        raise PlanError("output path must be absolute")
    if _has_symlink_component(target):
        raise PlanError("output path must not contain a symlink")
    root = Path(allowed_root).resolve() if allowed_root is not None else Path.home().resolve()
    parent = target.parent.resolve()
    if parent != root and root not in parent.parents:
        raise PlanError("output path is outside the authorized root")
    if not target.parent.is_dir():
        raise PlanError("output parent must be an existing directory")
    if target.exists():
        raise PlanError("output file already exists; refusing to overwrite")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(render_json(plan))
    return str(target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--approved-art-dir", type=Path)
    parser.add_argument("--landscape-wallpaper", type=Path)
    parser.add_argument("--terminal-refinement", type=Path)
    parser.add_argument("--enable-system-apps", action="store_true")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--output", type=Path, help="optional authorized JSON output file")
    parser.add_argument("--json", action="store_true", help="print JSON to stdout")
    args = parser.parse_args(argv)

    plan = build_plan(
        args.binary, art=args.approved_art_dir, wallpaper=args.landscape_wallpaper,
        terminal=args.terminal_refinement, native_apps=args.enable_system_apps,
        home=args.home,
    )
    if args.output is not None:
        try:
            write_plan(plan, args.output)
        except PlanError as exc:
            print("PREVIEW_PLAN_OUTPUT_UNAUTHORIZED:", exc, file=sys.stderr)
            return 2
        print("PREVIEW_PLAN_WRITTEN:", args.output)
    if args.json or args.output is None:
        print(render_json(plan), end="")
    else:
        print("PREVIEW_PLAN_" + plan["status"])
    return 0 if plan["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
