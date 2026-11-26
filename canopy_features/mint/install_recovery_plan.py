"""Fail-closed, read-only installer/recovery planner for Classic preview.

This module NEVER writes a file, launches a process, changes a session, uses
root or contacts a guest VM. It snapshots the exact managed desktop-entry
bytes/mode, describes bounded install/uninstall/recovery steps, and verifies
that an observed state matches a previously produced plan.

Native Linux Mint session acceptance is always ``NOT_RUN`` here: a dry-run or
a Python verifier cannot establish compositor, window-manager or guest-session
behavior. That evidence must come from an actual guest run.
"""

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from tools import register_classic_preview as menu

PLAN_SCHEMA = 1
NATIVE_MINT_ACCEPTANCE = "NOT_RUN"
MAX_DESKTOP_BYTES = 8192
MAX_MARKER_BYTES = 4096
MAX_PLAN_BYTES = 65536
MAX_STEPS = 8
OWNED_FILES = ("desktop", "manifest")
PROTECTED_PREFIXES = (
    "/etc", "/usr", "/var", "/opt", "/boot", "/proc", "/sys", "/dev",
    "/snap", "/root", "C:\\Windows", "C:\\Program Files",
    "C:\\Program Files (x86)", "C:\\ProgramData",
)

PLAN_KEYS = frozenset((
    "schema", "operation", "dry_run", "performs_changes", "privileged",
    "native_mint_session_acceptance", "guest_execution", "session_changes",
    "system_paths_written", "home", "owned_paths", "before", "after_expected",
    "steps", "rollback", "not_proven", "reasons", "auto_action_allowed",
    "safety", "session_restoration",
))


class RecoveryPlanError(ValueError):
    """An input or observed state failed a safety gate."""


def _text(value, name):
    """Translate hostile path types into the module's domain error."""
    if isinstance(value, bool) or not isinstance(value, (str, os.PathLike)):
        raise RecoveryPlanError(name + " must be a path string or PathLike")
    try:
        text = os.fspath(value)
    except Exception as exc:
        raise RecoveryPlanError(name + " must be a readable path string") from exc
    if not isinstance(text, str) or not text or "\x00" in text:
        raise RecoveryPlanError(name + " must be a nonempty path string")
    if any(not ch.isprintable() for ch in text):
        raise RecoveryPlanError(name + " contains a control character")
    return text


def assert_user_level_home(home):
    """Return an absolute, non-traversing home outside protected system roots."""
    raw = _text(home, "home")
    path = Path(raw)
    if not path.is_absolute() or os.pardir in path.parts:
        raise RecoveryPlanError("home must be an absolute, non-traversing path")
    try:
        menu._require_real_path_components(path, "home contains a symlink component")
    except menu.RegistrationError as exc:
        raise RecoveryPlanError(str(exc)) from exc
    normalized = os.path.normcase(os.path.abspath(raw))
    for prefix in PROTECTED_PREFIXES:
        probe = os.path.normcase(prefix).rstrip("\\/")
        if normalized == probe or any(
                normalized.startswith(probe + sep) for sep in ("/", "\\")):
            raise RecoveryPlanError("system-owned home is not user-level")
    return str(path)


def _owned_paths(home):
    """Return only the two owned files, rejecting an unexpected layout."""
    paths = menu.paths(home)
    expected = {"data", "parent", "folder", "apps", "desktop", "manifest"}
    if set(paths) != expected:
        raise RecoveryPlanError("unexpected owned-path layout")
    if (paths["data"] != Path(home) or paths["apps"].parent != Path(home)
            or paths["folder"].parent != Path(home) / "canopy"
            or paths["desktop"].parent != paths["apps"]
            or paths["manifest"].parent != paths["folder"]
            or paths["desktop"].name != menu.DESKTOP):
        raise RecoveryPlanError("unexpected owned destination")
    return paths


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _encoded(data):
    return base64.b64encode(data).decode("ascii")


def _decoded(value, limit, name):
    if not isinstance(value, str) or len(value) > 4 * limit + 8:
        raise RecoveryPlanError(name + " payload is not a bounded base64 string")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RecoveryPlanError(name + " payload is not valid base64") from exc
    if len(data) > limit:
        raise RecoveryPlanError(name + " payload exceeds its byte bound")
    return data


def _path_state(path, limit, name):
    """Capture exact state with lstat; never follow or read a symlink."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {"kind": "ABSENT", "size": None, "mode": None,
                "sha256": None, "payload_base64": None, "safe": True,
                "reason": None}
    except (OSError, ValueError) as exc:
        return {"kind": "UNREADABLE", "size": None, "mode": None,
                "sha256": None, "payload_base64": None, "safe": False,
                "reason": name + " could not be inspected"}
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "SYMLINK", "size": info.st_size, "mode": None,
                "sha256": None, "payload_base64": None, "safe": False,
                "reason": name + " is a symlink"}
    if not stat.S_ISREG(info.st_mode):
        return {"kind": "OTHER", "size": info.st_size, "mode": None,
                "sha256": None, "payload_base64": None, "safe": False,
                "reason": name + " is not a regular file"}
    if info.st_size > limit:
        return {"kind": "OVERSIZE", "size": info.st_size,
                "mode": stat.S_IMODE(info.st_mode), "sha256": None,
                "payload_base64": None, "safe": False,
                "reason": name + " exceeds its byte bound"}
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except (OSError, ValueError) as exc:
        return {"kind": "UNREADABLE", "size": info.st_size,
                "mode": stat.S_IMODE(info.st_mode), "sha256": None,
                "payload_base64": None, "safe": False,
                "reason": name + " could not be read"}
    if len(data) > limit:
        return {"kind": "OVERSIZE", "size": len(data),
                "mode": stat.S_IMODE(info.st_mode), "sha256": None,
                "payload_base64": None, "safe": False,
                "reason": name + " exceeds its byte bound"}
    return {"kind": "REGULAR_FILE", "size": len(data),
            "mode": stat.S_IMODE(info.st_mode), "sha256": _sha(data),
            "payload_base64": _encoded(data), "safe": True, "reason": None}


def _projected(path, data, mode):
    if len(data) > MAX_DESKTOP_BYTES:
        raise RecoveryPlanError("projected entry exceeds its byte bound")
    # Windows chmod only maps the owner write bit; recording an unachievable
    # POSIX mode would make a correct install verify as a false mismatch.
    effective = 0o666 if os.name == "nt" else mode
    return {"kind": "REGULAR_FILE", "size": len(data), "mode": effective,
            "sha256": _sha(data), "payload_base64": _encoded(data),
            "safe": True, "reason": None, "target": str(path)}


def _absent(path):
    return {"kind": "ABSENT", "size": None, "mode": None, "sha256": None,
            "payload_base64": None, "safe": True, "reason": None,
            "target": str(path)}


def _safe_status(home):
    try:
        return menu.status(home)
    except (OSError, ValueError, TypeError):
        return "UNSAFE"


def snapshot_desktop_entry(home):
    """Snapshot the exact user-level desktop-entry state without changes."""
    normalized = assert_user_level_home(home)
    owned = _owned_paths(normalized)
    desktop = _path_state(owned["desktop"], MAX_DESKTOP_BYTES, "desktop entry")
    manifest = _path_state(owned["manifest"], MAX_MARKER_BYTES, "ownership marker")
    autostart = _path_state(
        Path(normalized) / ".config" / "autostart" / menu.DESKTOP,
        MAX_DESKTOP_BYTES, "xdg autostart entry")
    xsessions = _path_state(
        Path(normalized) / ".local" / "share" / "xsessions" / menu.DESKTOP,
        MAX_DESKTOP_BYTES, "xdg session entry")
    status = _safe_status(normalized)
    reasons = []
    if status == "UNSAFE":
        reasons.append("managed path is unsafe")
    for name, state in (("desktop", desktop), ("manifest", manifest)):
        if not state["safe"]:
            reasons.append("unexpected_path:" + name)
    for name, state in (("xdg_autostart", autostart), ("xdg_session", xsessions)):
        # Any managed-name autostart/session entry is a session change, even
        # when it is a well-formed regular file with our preview name.
        if not state["safe"] or state["kind"] != "ABSENT":
            reasons.append("unexpected_path:" + name)
    if (desktop["safe"] and manifest["safe"]
            and desktop["kind"] == "REGULAR_FILE"
            and manifest["kind"] == "REGULAR_FILE"):
        entry = _decoded(desktop["payload_base64"], MAX_DESKTOP_BYTES, "desktop")
        marker = _decoded(manifest["payload_base64"], MAX_MARKER_BYTES, "marker")
        expected = _marker_digest(marker)
        if expected is None or expected != _sha(entry):
            reasons.append("ownership_checksum_mismatch")
    return {
        "schema": PLAN_SCHEMA,
        "home": normalized,
        "status": status,
        "paths": {key: str(value) for key, value in owned.items()},
        "desktop": desktop,
        "manifest": manifest,
        "session_entry_probes": {"xdg_autostart": autostart,
                                 "xdg_session": xsessions},
        "safe": not reasons,
        "reasons": reasons,
    }


def _no_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryPlanError("duplicate JSON key: " + str(key))
        result[key] = value
    return result


def _marker_digest(data):
    try:
        marker = json.loads(data.decode("utf-8"),
                            object_pairs_hook=_no_duplicate_pairs)
    except (RecoveryPlanError, OSError, UnicodeError, ValueError):
        return None
    if (not isinstance(marker, dict) or set(marker) != {"schema", "sha256"}
            or type(marker["schema"]) is not int or marker["schema"] != 1
            or not isinstance(marker["sha256"], str)
            or len(marker["sha256"]) != 64
            or any(ch not in "0123456789abcdef" for ch in marker["sha256"])):
        return None
    return marker["sha256"]


def _common(operation, home, snapshot):
    """Fields shared by every plan: no changes, no privilege, no guest pass."""
    return {
        "schema": PLAN_SCHEMA,
        "operation": operation,
        "dry_run": True,
        "performs_changes": False,
        "privileged": False,
        "native_mint_session_acceptance": NATIVE_MINT_ACCEPTANCE,
        "guest_execution": NATIVE_MINT_ACCEPTANCE,
        "session_changes": [],
        "system_paths_written": [],
        "home": snapshot["home"],
        "owned_paths": {key: snapshot["paths"][key] for key in OWNED_FILES},
        "before": {key: snapshot[key] for key in OWNED_FILES},
        "steps": [],
        "rollback": [],
        "not_proven": [
            "No Linux Mint guest was contacted.",
            "Native Mint session launch and compositor behavior: " +
            NATIVE_MINT_ACCEPTANCE,
            "Window manager, focus handoff and logout/re-entry: " +
            NATIVE_MINT_ACCEPTANCE,
            "No destructive or system-wide change was executed or authorized.",
        ],
        "reasons": list(snapshot["reasons"]),
        "auto_action_allowed": False,
        "safety": "DRY_RUN_ONLY",
        "session_restoration": {
            "strategy": "NO_OP_SESSION_NEVER_CHANGED",
            "display_manager": "UNCHANGED",
            "compositor": "UNCHANGED",
            "acceptance": NATIVE_MINT_ACCEPTANCE,
        },
    }


def _steps(*entries):
    result = [dict(entry) for entry in entries]
    if len(result) > MAX_STEPS:
        raise RecoveryPlanError("plan exceeds the bounded step count")
    for order, step in enumerate(result, 1):
        step["order"] = order
        step["privileged"] = False
    return result


def plan_install(home, binary, *, art=None, wallpaper=None, terminal=None,
                 native_apps=False):
    """Describe an install that writes only the two owned user files."""
    snapshot = snapshot_desktop_entry(home)
    if not snapshot["safe"] or snapshot["status"] != "NOT_INSTALLED":
        raise RecoveryPlanError("install refused: " +
                                "; ".join(snapshot["reasons"] or
                                          [snapshot["status"]]))
    try:
        payload = menu.desktop_entry(binary, art=art, wallpaper=wallpaper,
                                     terminal=terminal, native_apps=native_apps)
        marker = menu.ownership_marker(payload)
    except menu.RegistrationError as exc:
        raise RecoveryPlanError(str(exc)) from exc
    if len(payload) > MAX_DESKTOP_BYTES or len(marker) > MAX_MARKER_BYTES:
        raise RecoveryPlanError("projected entry exceeds its byte bound")
    plan = _common("install", home, snapshot)
    plan["after_expected"] = {
        "status": "INSTALLED",
        "desktop": _projected(snapshot["paths"]["desktop"], payload, 0o644),
        "manifest": _projected(snapshot["paths"]["manifest"], marker, 0o600),
    }
    plan["steps"] = _steps(
        {"phase": "snapshot", "description": "Recheck exact owned-entry state."},
        {"phase": "validate-binary",
         "description": "Require an absolute, executable, non-symlink binary.",
         "path": _text(binary, "binary")},
        {"phase": "write-desktop-entry",
         "description": "Exclusively create the owned user desktop entry.",
         "target": plan["owned_paths"]["desktop"],
         "bytes_bound": MAX_DESKTOP_BYTES,
         "sha256": _sha(payload)},
        {"phase": "write-ownership-marker",
         "description": "Exclusively create the owned ownership marker.",
         "target": plan["owned_paths"]["manifest"],
         "bytes_bound": MAX_MARKER_BYTES,
         "sha256": _sha(marker)},
        {"phase": "verify",
         "description": "Recheck bytes, mode and status after a real install.",
         "verdict": NATIVE_MINT_ACCEPTANCE},
    )
    plan["rollback"] = [
        {"order": 1, "action": "unlink_created_file",
         "target": plan["owned_paths"]["manifest"], "bytes_bound": 0},
        {"order": 2, "action": "unlink_created_file",
         "target": plan["owned_paths"]["desktop"], "bytes_bound": 0},
    ]
    return plan


def _installed_state(snapshot):
    """Return and validate exact bytes of an installed, owned entry."""
    if not snapshot["safe"] or snapshot["status"] != "INSTALLED":
        raise RecoveryPlanError("owned entry is not installed and exact")
    entry = _decoded(snapshot["desktop"]["payload_base64"],
                     MAX_DESKTOP_BYTES, "desktop")
    marker = _decoded(snapshot["manifest"]["payload_base64"],
                      MAX_MARKER_BYTES, "marker")
    if _marker_digest(marker) != _sha(entry):
        raise RecoveryPlanError("ownership checksum mismatch")
    return entry, marker


def plan_uninstall(home):
    """Describe a bounded uninstall that deletes only exact-owned files."""
    snapshot = snapshot_desktop_entry(home)
    entry, marker = _installed_state(snapshot)
    plan = _common("uninstall", home, snapshot)
    plan["after_expected"] = {
        "status": "NOT_INSTALLED",
        "desktop": _absent(snapshot["paths"]["desktop"]),
        "manifest": _absent(snapshot["paths"]["manifest"]),
    }
    plan["steps"] = _steps(
        {"phase": "snapshot", "description": "Recheck exact owned-entry state."},
        {"phase": "verify-ownership", "description": "Match bytes to marker.",
         "sha256": _sha(entry)},
        {"phase": "unlink-desktop", "description": "Delete only the owned entry.",
         "target": plan["owned_paths"]["desktop"],
         "sha256": _sha(entry)},
        {"phase": "unlink-manifest", "description": "Delete only the owned marker.",
         "target": plan["owned_paths"]["manifest"],
         "sha256": _sha(marker)},
        {"phase": "verify", "description": "Confirm both owned paths are absent.",
         "verdict": NATIVE_MINT_ACCEPTANCE},
    )
    plan["rollback"] = [
        {"order": 1, "action": "restore_exact_bytes_and_mode",
         "target": plan["owned_paths"]["desktop"],
         "payload_base64": _encoded(entry),
         "mode": snapshot["desktop"]["mode"],
         "bytes_bound": MAX_DESKTOP_BYTES},
    ]
    return plan


def plan_recovery(home):
    """Describe recovery to an untouched Cinnamon session.

    The installer never changes the session, so recovery is limited to
    removing an exact-owned preview entry. A modified/unmanaged state requires
    manual review: no automatic deletion is proposed.
    """
    snapshot = snapshot_desktop_entry(home)
    blocking = [reason for reason in snapshot["reasons"]
                if reason != "ownership_checksum_mismatch"]
    if blocking:
        raise RecoveryPlanError("recovery refused: " + "; ".join(blocking))
    plan = _common("recover", home, snapshot)
    plan["session_restoration"] = {
        "strategy": "NO_OP_SESSION_NEVER_CHANGED",
        "display_manager": "UNCHANGED",
        "compositor": "UNCHANGED",
        "acceptance": NATIVE_MINT_ACCEPTANCE,
    }
    if snapshot["status"] == "NOT_INSTALLED":
        plan["after_expected"] = {
            "status": "NOT_INSTALLED",
            "desktop": _absent(snapshot["paths"]["desktop"]),
            "manifest": _absent(snapshot["paths"]["manifest"]),
        }
        plan["steps"] = _steps(
            {"phase": "snapshot", "description": "Confirm no owned files exist."},
            {"phase": "verify", "description": "No recovery action is needed.",
             "verdict": NATIVE_MINT_ACCEPTANCE},
        )
        return plan
    if snapshot["status"] != "INSTALLED":
        plan["auto_action_allowed"] = False
        plan["reasons"].append("manual_review_required")
        plan["after_expected"] = None
        plan["steps"] = _steps(
            {"phase": "snapshot", "description": "Preserve unmanaged state."},
            {"phase": "manual-review",
             "description": "Do not delete a modified or unmanaged entry.",
             "verdict": NATIVE_MINT_ACCEPTANCE},
        )
        return plan
    uninstall = plan_uninstall(home)
    plan["after_expected"] = uninstall["after_expected"]
    plan["steps"] = uninstall["steps"]
    plan["rollback"] = uninstall["rollback"]
    return plan


def verify_plan(plan):
    """Validate a plan structurally and cryptographically; never mutate it."""
    if not isinstance(plan, dict) or set(plan) != PLAN_KEYS:
        return {"verdict": "FAIL", "reasons": ["unexpected_plan_shape"]}
    reasons = []
    if (type(plan["schema"]) is not int or plan["schema"] != PLAN_SCHEMA
            or plan["dry_run"] is not True
            or plan["performs_changes"] is not False
            or plan["privileged"] is not False
            or plan["native_mint_session_acceptance"] != NATIVE_MINT_ACCEPTANCE
            or plan["guest_execution"] != NATIVE_MINT_ACCEPTANCE
            or plan["session_changes"] != []
            or plan["system_paths_written"] != []):
        reasons.append("unsafe_claim")
    if plan["operation"] not in ("install", "uninstall", "recover"):
        reasons.append("unknown_operation")
    if plan["session_restoration"] != {
            "strategy": "NO_OP_SESSION_NEVER_CHANGED",
            "display_manager": "UNCHANGED",
            "compositor": "UNCHANGED",
            "acceptance": NATIVE_MINT_ACCEPTANCE}:
        reasons.append("session_change_claimed")
    if (not isinstance(plan["not_proven"], list)
            or not any("NOT_RUN" in note for note in plan["not_proven"]
                       if isinstance(note, str))):
        reasons.append("missing_not_run_label")
    after = plan["after_expected"]
    if isinstance(after, dict):
        expected_status = after.get("status")
        pieces = [after.get(name) for name in OWNED_FILES]
        if any(not isinstance(piece, dict) for piece in pieces):
            reasons.append("invalid_expected_files")
            kinds = (None, None)
        else:
            kinds = tuple(piece.get("kind") for piece in pieces)
        if expected_status == "INSTALLED" and kinds != ("REGULAR_FILE",
                                                        "REGULAR_FILE"):
            reasons.append("installed_status_without_owned_files")
        elif expected_status == "NOT_INSTALLED" and kinds != ("ABSENT",
                                                              "ABSENT"):
            reasons.append("absent_status_with_owned_files")
        elif expected_status not in ("INSTALLED", "NOT_INSTALLED"):
            reasons.append("unknown_expected_status")
    elif after is not None:
        reasons.append("invalid_expected_state")
    try:
        home = assert_user_level_home(plan["home"])
        owned = _owned_paths(home)
        allowed = {str(owned[key]) for key in OWNED_FILES}
        if set(plan["owned_paths"]) != set(OWNED_FILES):
            reasons.append("unexpected_owned_paths")
        elif any(plan["owned_paths"][key] != str(owned[key])
                 for key in OWNED_FILES):
            reasons.append("owned_path_outside_user_home")
        before = plan["before"]
        after_states = plan["after_expected"] or {}
        for name in OWNED_FILES:
            for state in (before.get(name), after_states.get(name)):
                if state is None:
                    continue
                if ("target" in state
                        and state["target"] != str(owned[name])):
                    reasons.append("unexpected_path:" + name)
                    continue
                payload = state.get("payload_base64")
                if payload is None:
                    continue
                data = _decoded(payload, MAX_DESKTOP_BYTES, name)
                if state.get("sha256") != _sha(data) or state.get("size") != len(data):
                    reasons.append("snapshot_checksum_mismatch:" + name)
        steps = plan["steps"]
        if (not isinstance(steps, list) or len(steps) > MAX_STEPS
                or [step.get("order") for step in steps]
                != list(range(1, len(steps) + 1))):
            reasons.append("invalid_steps")
        for step in steps:
            if step.get("privileged") is not False:
                reasons.append("privileged_step")
            target = step.get("target")
            if target is not None and target not in allowed:
                reasons.append("step_outside_owned_paths")
        for item in plan["rollback"]:
            if item.get("target") not in allowed:
                reasons.append("rollback_outside_owned_paths")
            if type(item.get("bytes_bound")) is not int or not (
                    0 <= item["bytes_bound"] <= MAX_DESKTOP_BYTES):
                reasons.append("unbounded_rollback")
            payload = item.get("payload_base64")
            if payload is not None:
                _decoded(payload, MAX_DESKTOP_BYTES, "rollback")
    except (RecoveryPlanError, AttributeError, TypeError, ValueError) as exc:
        reasons.append("invalid_plan_value:" + type(exc).__name__)
    return {"verdict": "FAIL" if reasons else "PASS",
            "reasons": reasons}


def verify_recovery(home, expected):
    """Compare observed exact state with an approved dry-run expectation."""
    checked = verify_plan(expected)
    if checked["verdict"] != "PASS":
        return {"verdict": "FAIL", "reasons": ["plan_" + r
                                               for r in checked["reasons"]]}
    try:
        observed_home = assert_user_level_home(home)
    except RecoveryPlanError as exc:
        return {"verdict": "FAIL", "reasons": ["home_" + str(exc)]}
    if observed_home != expected["home"]:
        return {"verdict": "FAIL", "reasons": ["home_mismatch"]}
    snapshot = snapshot_desktop_entry(home)
    reasons = list(snapshot["reasons"])
    wanted = expected["after_expected"]
    if wanted is None:
        blocking = [reason for reason in reasons
                    if reason != "ownership_checksum_mismatch"]
        return {"verdict": "FAIL" if blocking else "NEEDS_MANUAL_REVIEW",
                "reasons": blocking or ["modified_or_unmanaged_state"]}
    if snapshot["status"] != wanted["status"]:
        reasons.append("status_mismatch")
    for name in OWNED_FILES:
        target = wanted[name]
        observed = snapshot[name]
        if observed["kind"] != target["kind"]:
            reasons.append("kind_mismatch:" + name)
            continue
        if target["kind"] == "REGULAR_FILE":
            for field in ("sha256", "mode", "size", "payload_base64"):
                if observed[field] != target[field]:
                    reasons.append(field + "_mismatch:" + name)
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons}


def verify_plan_file(path):
    """Read a bounded JSON plan file; duplicate keys fail closed."""
    raw = _text(path, "plan file")
    file_path = Path(raw)
    if not file_path.is_absolute() or file_path.suffix != ".json":
        return {"verdict": "FAIL", "reasons": ["plan_file_must_be_absolute_json"]}
    try:
        menu._require_real_path_components(file_path, "unsafe plan file")
        info = file_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PLAN_BYTES:
            return {"verdict": "FAIL", "reasons": ["unsafe_plan_file"]}
        with open(file_path, "rb") as handle:
            data = handle.read(MAX_PLAN_BYTES + 1)
        if len(data) > MAX_PLAN_BYTES:
            return {"verdict": "FAIL", "reasons": ["plan_file_too_large"]}
        parsed = json.loads(data.decode("utf-8"),
                            object_pairs_hook=_no_duplicate_pairs)
    except (RecoveryPlanError, OSError, UnicodeError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, RecoveryPlanError) else type(exc).__name__
        return {"verdict": "FAIL", "reasons": ["unreadable_plan:" + detail]}
    result = verify_plan(parsed)
    result["sha256"] = _sha(data)
    return result


def main(argv=None):
    """Read-only CLI: emit a plan/snapshot or verify one against live state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True)
    parser.add_argument("--action", required=True,
                        choices=("snapshot", "install", "uninstall", "recover",
                                 "verify"))
    parser.add_argument("--binary")
    parser.add_argument("--approved-art-dir")
    parser.add_argument("--landscape-wallpaper")
    parser.add_argument("--terminal-refinement")
    parser.add_argument("--enable-system-apps", action="store_true")
    parser.add_argument("--plan")
    args = parser.parse_args(argv)
    try:
        if args.action == "snapshot":
            result = snapshot_desktop_entry(args.home)
        elif args.action == "install":
            result = plan_install(
                args.home, args.binary, art=args.approved_art_dir,
                wallpaper=args.landscape_wallpaper,
                terminal=args.terminal_refinement,
                native_apps=args.enable_system_apps)
        elif args.action == "uninstall":
            result = plan_uninstall(args.home)
        elif args.action == "recover":
            result = plan_recovery(args.home)
        else:
            if args.plan is None:
                raise RecoveryPlanError("verify requires --plan")
            checked = verify_plan_file(args.plan)
            if checked["verdict"] != "PASS":
                result = checked
            else:
                with open(args.plan, "r", encoding="utf-8") as handle:
                    expected = json.load(handle,
                                         object_pairs_hook=_no_duplicate_pairs)
                result = verify_recovery(args.home, expected)
    except (RecoveryPlanError, menu.RegistrationError, OSError, ValueError) as exc:
        print("CANOPY_INSTALL_RECOVERY_FAIL:", exc, file=sys.stderr)
        return 1
    print("CANOPY_INSTALL_RECOVERY:", json.dumps(result, sort_keys=True))
    if args.action == "verify" and result.get("verdict") not in (
            "PASS", "NEEDS_MANUAL_REVIEW"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
