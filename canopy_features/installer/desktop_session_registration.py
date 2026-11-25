"""Offline planner for a reversible user-level Classic X11 session entry.

Issue #107 concerns the real Mint session/release blocker. This module is the
smallest reversible step toward it: it plans user-owned XDG session metadata
while leaving the Cinnamon X11 session manager, compositor and display manager
untouched. It does **not** register a session, start a process, change a host
setting, or execute any privileged action. Every result is a description for a
separate, explicitly authorized executor.

Existing Mint/XDG contracts are reused rather than reimplemented:

* :mod:`canopy_features.installer.xdg_user_paths` resolves and validates the
  per-user XDG data target (root, traversal and symlinked parents are refused);
* :mod:`canopy_features.installer.session_entry_validation` validates the
  narrow ``[Desktop Entry]`` metadata shape and the fixed absolute ``Exec``;
* :mod:`canopy_features.installer.uninstall_integrity` normalizes the exact
  SHA-256 ownership manifest; the marker shape matches the reversible
  ``tools/register_classic_preview.py`` ownership marker.

The plan records the exact SHA-256 of the entry bytes and of the marker bytes.
``dry-run`` describes writes, ``register`` plans writes only onto an empty
target, and ``unregister`` plans removals only after both hashes match the
recorded ownership. A partial write/removal has an explicit byte-exact unwind.

A produced plan is NOT proof of Mint display-manager acceptance, a working
desktop, a trusted package, or owner visual approval.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional, Tuple

from canopy_features.installer import session_entry_validation as _session
from canopy_features.installer import uninstall_integrity as _integrity
from canopy_features.installer import xdg_user_paths as _xdg

SCHEMA = 1
ACTIONS = frozenset(("dry-run", "register", "unregister"))
ENTRY_SUBDIR = "xsessions"
MARKER_RELATIVE = "canopy/classic-session/ownership.json"
TOP_KEYS = frozenset((
    "schema", "action", "home", "env", "entry_name", "entry_text", "observed",
))
OBSERVED_KEYS = frozenset((
    "entry_sha256", "marker_sha256", "recorded_entry_sha256",
))
MAX_HOME_CHARS = 512
MAX_ENTRY_NAME_CHARS = 96
MAX_ENV_ENTRIES = 64
MAX_ENV_CHARS = 512
MAX_UNWIND_ACTIONS = 8

_HEX = frozenset("0123456789abcdef")
_ENTRY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.desktop\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SYSTEM_HOME_PARTS = frozenset((
    "usr", "etc", "var", "opt", "bin", "sbin", "lib", "lib64", "boot",
    "proc", "sys", "dev", "run", "snap",
))
_WINDOWS_SYSTEM_PARTS = frozenset((
    "windows", "program files", "program files (x86)", "programdata",
))


class DesktopSessionRegistrationError(ValueError):
    """Malformed, unsafe or unrecognized session registration input."""


@dataclass(frozen=True)
class PlanStep:
    """One described operation; ``status`` is never an execution claim."""

    order: int
    phase: str
    detail: str
    relative: str
    sha256: str
    status: str

    def as_dict(self):
        return {
            "order": self.order,
            "phase": self.phase,
            "detail": self.detail,
            "relative": self.relative,
            "sha256": self.sha256,
            "status": self.status,
        }


@dataclass(frozen=True)
class Unwind:
    """Byte-exact compensation for a failed partial write or removal."""

    trigger: str
    verify_sha256: str
    restore_files: Tuple[Tuple[str, str], ...]
    remove_files: Tuple[str, ...]
    detail: str

    def as_dict(self):
        return {
            "trigger": self.trigger,
            "verify_sha256": self.verify_sha256,
            "restore_files": [list(pair) for pair in self.restore_files],
            "remove_files": list(self.remove_files),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SessionRegistrationPlan:
    """Immutable, side-effect-free plan; no host change has been performed."""

    action: str
    safe: bool
    entry_relative: str
    marker_relative: str
    entry_sha256: str
    marker_sha256: str
    steps: Tuple[PlanStep, ...]
    unwind: Tuple[Unwind, ...]
    remove_files: Tuple[str, ...]
    blockers: Tuple[str, ...]

    def as_dict(self):
        """Fresh JSON-ready snapshot with hardcoded negative claims."""
        if type(self.action) is not str or self.action not in ACTIONS:
            raise DesktopSessionRegistrationError("unsupported plan action")
        if type(self.safe) is not bool:
            raise DesktopSessionRegistrationError("unsafe plan status")
        if (type(self.entry_sha256) is not str
                or not _is_sha(self.entry_sha256)
                or type(self.marker_sha256) is not str
                or not _is_sha(self.marker_sha256)):
            raise DesktopSessionRegistrationError("invalid ownership hash")
        if (type(self.steps) is not tuple or not self.steps
                or len(self.steps) > MAX_UNWIND_ACTIONS
                or type(self.unwind) is not tuple
                or len(self.unwind) > MAX_UNWIND_ACTIONS
                or any(type(step) is not PlanStep for step in self.steps)
                or any(type(item) is not Unwind for item in self.unwind)):
            raise DesktopSessionRegistrationError("unbounded plan")
        for field in (self.remove_files, self.blockers):
            if (type(field) is not tuple or len(field) > MAX_UNWIND_ACTIONS
                    or any(type(item) is not str for item in field)):
                raise DesktopSessionRegistrationError("invalid plan token list")
        if type(self.entry_relative) is not str or type(self.marker_relative) is not str:
            raise DesktopSessionRegistrationError("invalid ownership path")
        try:
            _integrity.normalize_manifest({
                "schema": SCHEMA,
                "files": {
                    self.entry_relative: self.entry_sha256,
                    self.marker_relative: self.marker_sha256,
                },
            })
        except (_integrity.UninstallIntegrityError, TypeError, ValueError):
            raise DesktopSessionRegistrationError("invalid ownership path") from None
        return {
            "status": "DESKTOP_SESSION_PLAN",
            "schema": SCHEMA,
            "action": self.action,
            "safe": self.safe,
            "entry_relative": self.entry_relative,
            "marker_relative": self.marker_relative,
            "entry_sha256": self.entry_sha256,
            "marker_sha256": self.marker_sha256,
            "steps": [step.as_dict() for step in self.steps],
            "unwind": [item.as_dict() for item in self.unwind],
            "remove_files": list(self.remove_files),
            "blockers": list(self.blockers),
            "executes_host_changes": False,
            "privileged": False,
            "session_started": False,
            "display_manager_changed": False,
            "cinnamon_session_replaced": False,
            "compositor_replaced": False,
            "package_installed": False,
            "linux_mint_acceptance_proven": False,
            "owner_visual_approval": False,
        }


@dataclass(frozen=True)
class RollbackDecision:
    """Pure answer to 'what may a compensating executor undo?'."""

    safe: bool
    restore_files: Tuple[Tuple[str, str], ...]
    remove_files: Tuple[str, ...]
    blockers: Tuple[str, ...]

    def as_dict(self):
        return {
            "safe": self.safe,
            "restore_files": [list(pair) for pair in self.restore_files],
            "remove_files": list(self.remove_files),
            "blockers": list(self.blockers),
        }


def _is_sha(value):
    return (type(value) is str and len(value) == 64
            and all(char in _HEX for char in value))


def _text(value, label, maximum):
    if type(value) is not str or not value or len(value) > maximum:
        raise DesktopSessionRegistrationError("invalid " + label)
    if _CONTROL.search(value):
        raise DesktopSessionRegistrationError("control character in " + label)
    return value


def _sha(value, label, *, allow_none=False):
    if value is None and allow_none:
        return None
    if not _is_sha(value):
        raise DesktopSessionRegistrationError("invalid " + label)
    return value


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _home(text):
    text = _text(text, "home", MAX_HOME_CHARS)
    try:
        path = Path(text)
        normalized = os.path.normpath(text)
    except (OSError, ValueError) as exc:
        raise DesktopSessionRegistrationError("invalid home") from exc
    if not path.is_absolute() or Path(normalized).parent == Path(normalized):
        raise DesktopSessionRegistrationError("home must be an absolute user directory")
    if os.name != "nt":
        parts = PurePosixPath(normalized).parts
        if len(parts) < 2 or parts[1] in _SYSTEM_HOME_PARTS:
            raise DesktopSessionRegistrationError("home must not be a system directory")
    elif any(part.casefold() in _WINDOWS_SYSTEM_PARTS
             for part in Path(normalized).parts[1:]):
        raise DesktopSessionRegistrationError("home must not be a system directory")
    return normalized


def _env(value):
    if type(value) is not dict or len(value) > MAX_ENV_ENTRIES:
        raise DesktopSessionRegistrationError("env must be a bounded object")
    result = {}
    for key, item in value.items():
        _text(key, "env name", MAX_ENV_CHARS)
        _text(item, "env value", MAX_ENV_CHARS)
        result[key] = item
    return result


def _observed(value):
    if type(value) is not dict or not frozenset(value) <= OBSERVED_KEYS:
        raise DesktopSessionRegistrationError("observed must be a bounded object")
    return {
        key: _sha(value.get(key), key, allow_none=True)
        for key in sorted(OBSERVED_KEYS)
    }


def _entry_name(value):
    value = _text(value, "entry name", MAX_ENTRY_NAME_CHARS)
    if not _ENTRY_NAME.fullmatch(value):
        raise DesktopSessionRegistrationError("unsafe session entry name")
    return value


def _entry_bytes(text):
    if type(text) is not str or not text or len(text) > _session.MAX_ENTRY_BYTES:
        raise DesktopSessionRegistrationError("invalid session entry text")
    try:
        raw = text.encode("utf-8")
    except UnicodeError as exc:
        raise DesktopSessionRegistrationError("session entry is not UTF-8") from exc
    if not raw or len(raw) > _session.MAX_ENTRY_BYTES:
        raise DesktopSessionRegistrationError("session entry exceeds 16 KiB")
    try:
        fields = _session._parse(text)
        name = _session._clean_string(
            fields["Name"], "Name", _session.MAX_NAME_CHARS)
        _session._safe_exec_path(fields["Exec"])
        if "Comment" in fields:
            _session._clean_string(
                fields["Comment"], "Comment", _session.MAX_COMMENT_CHARS)
        if "Icon" in fields:
            _session._clean_string(
                fields["Icon"], "Icon", _session.MAX_ICON_CHARS)
    except (_session.SessionEntryError, KeyError, TypeError, ValueError) as exc:
        raise DesktopSessionRegistrationError("unsafe session entry text") from exc
    if type(name) is not str or not name:
        raise DesktopSessionRegistrationError("unsafe session entry text")
    return raw


def _marker_bytes(entry_sha256):
    payload = {"schema": SCHEMA, "sha256": entry_sha256}
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8")


def _targets(home, env, entry_name):
    entry_relative = ENTRY_SUBDIR + "/" + entry_name
    try:
        entry = _xdg.target("data", entry_relative, home=home, env=env)
        marker = _xdg.target("data", MARKER_RELATIVE, home=home, env=env)
    except (_xdg.UnsafeXdgPath, TypeError, ValueError, OSError) as exc:
        raise DesktopSessionRegistrationError("unsafe XDG session target") from exc
    return entry_relative, str(entry), str(marker)


def _step(order, phase, detail, relative="", sha256="", status="PLANNED"):
    return PlanStep(order, phase, detail, relative, sha256, status)


def _write_steps(entry_relative, marker_relative, entry_sha256, marker_sha256):
    return (
        _step(1, "preserve-session",
              "Cinnamon X11 session, session manager and compositor are unchanged.",
              status="DESCRIBED_NOT_RUN"),
        _step(2, "validate-target",
              "XDG data target stays inside the user home without symlinks.",
              relative=entry_relative, status="OK"),
        _step(3, "write-entry", "Write exact UTF-8 session entry bytes.",
              relative=entry_relative, sha256=entry_sha256),
        _step(4, "write-marker", "Write exact-byte ownership marker only on an empty target.",
              relative=marker_relative, sha256=marker_sha256),
        _step(5, "verify", "Recheck entry and marker SHA-256 after write.",
              relative=entry_relative),
    )


def _removal_steps(entry_relative, marker_relative, entry_sha256,
                   marker_sha256, verified):
    return (
        _step(1, "preserve-session",
              "Cinnamon X11 session, session manager and compositor are unchanged.",
              status="DESCRIBED_NOT_RUN"),
        _step(2, "verify-ownership", "Both exact-byte ownership hashes must match.",
              relative=entry_relative, sha256=entry_sha256,
              status="OK" if verified else "BLOCKED"),
        _step(3, "remove-entry", "Remove only the verified session entry file.",
              relative=entry_relative, sha256=entry_sha256),
        _step(4, "remove-marker", "Remove only the verified ownership marker.",
              relative=marker_relative, sha256=marker_sha256),
        _step(5, "verify-removed", "Confirm both owned paths are gone.",
              relative=entry_relative),
    )


def build_plan(record):
    """Validate a bounded request and return an immutable, side-effect-free plan.

    Malformed or hostile shapes raise :class:`DesktopSessionRegistrationError`.
    Unsafe but well-formed states (an occupied target, a modified owned file,
    a missing ownership record) produce a plan with ``safe=False``, no removal
    actions and explanatory fixed-token blockers. No path is created, written,
    deleted or resolved to a host process.
    """
    if type(record) is not dict or frozenset(record) != TOP_KEYS:
        raise DesktopSessionRegistrationError("unexpected registration key set")
    schema = record["schema"]
    if type(schema) is not int or schema != SCHEMA:
        raise DesktopSessionRegistrationError("unsupported registration schema")
    action = record["action"]
    if type(action) is not str or action not in ACTIONS:
        raise DesktopSessionRegistrationError("unsupported registration action")
    home = _home(record["home"])
    env = _env(record["env"])
    entry_name = _entry_name(record["entry_name"])
    observed = _observed(record["observed"])
    entry_text = record["entry_text"]

    blockers = []
    if action == "unregister":
        if entry_text is not None:
            raise DesktopSessionRegistrationError(
                "unregister does not accept entry text")
        raw = None
        entry_sha256 = observed["recorded_entry_sha256"]
        if entry_sha256 is None:
            blockers.append("MISSING recorded ownership hash")
            entry_sha256 = ""
            marker_sha256 = ""
        else:
            marker_sha256 = _digest(_marker_bytes(entry_sha256))
            if observed["entry_sha256"] != entry_sha256:
                blockers.append("OWNERSHIP MISMATCH: session entry")
            if observed["marker_sha256"] != marker_sha256:
                blockers.append("OWNERSHIP MISMATCH: ownership marker")
    else:
        raw = _entry_bytes(entry_text)
        entry_sha256 = _digest(raw)
        marker_sha256 = _digest(_marker_bytes(entry_sha256))
        if action == "register" and (
                observed["entry_sha256"] is not None
                or observed["marker_sha256"] is not None):
            blockers.append("EXISTING OR UNMANAGED SESSION TARGET")

    entry_relative, entry_path, marker_path = _targets(home, env, entry_name)
    marker_relative = MARKER_RELATIVE
    manifest = {
        "schema": SCHEMA,
        "files": {entry_relative: entry_sha256, marker_relative: marker_sha256},
    }
    try:
        _integrity.normalize_manifest(manifest)
    except _integrity.UninstallIntegrityError as exc:
        blockers.append("unsafe ownership manifest: " + str(exc))

    if action == "unregister":
        steps = _removal_steps(entry_relative, marker_relative, entry_sha256,
                               marker_sha256, not blockers)
        unwind = (Unwind(
            "marker_removal_failed", entry_sha256,
            ((entry_relative, entry_sha256),), (),
            "If marker removal fails after entry removal, recreate the entry "
            "from its exact recorded SHA-256.",
        ),)
        remove_files = (entry_relative, marker_relative) if not blockers else ()
    else:
        steps = _write_steps(entry_relative, marker_relative, entry_sha256,
                             marker_sha256)
        unwind = (Unwind(
            "marker_write_failed", entry_sha256, (),
            (entry_relative,),
            "If marker creation fails, remove only the new entry while its "
            "SHA-256 still matches the planned bytes.",
        ),)
        remove_files = ()

    if not (entry_path and marker_path):
        # Defensive: target strings are only descriptions, never execution.
        raise DesktopSessionRegistrationError("incomplete target description")

    return SessionRegistrationPlan(
        action=action, safe=not blockers, entry_relative=entry_relative,
        marker_relative=marker_relative, entry_sha256=entry_sha256,
        marker_sha256=marker_sha256, steps=steps, unwind=unwind,
        remove_files=remove_files, blockers=tuple(blockers),
    )


def rollback_decision(plan, observed):
    """Decide a byte-exact unwind without touching the host.

    For a failed ``register``, the newly written entry may only be removed if
    its current hash still equals the planned hash. For a failed ``unregister``,
    the entry may only be recreated when it is absent; an unexpected file is
    never overwritten.
    """
    if not isinstance(plan, SessionRegistrationPlan):
        raise DesktopSessionRegistrationError("plan must be a registration plan")
    if type(plan.action) is not str or plan.action not in ACTIONS:
        raise DesktopSessionRegistrationError("unsupported plan action")
    if not plan.safe:
        return RollbackDecision(False, (), (), ("UNSAFE BASE PLAN",))
    seen = _observed(observed)
    blockers = []
    if plan.action == "unregister":
        if seen["entry_sha256"] is not None:
            blockers.append("OWNERSHIP MISMATCH: entry still present")
        else:
            return RollbackDecision(
                True, ((plan.entry_relative, plan.entry_sha256),), (), ())
    elif plan.action == "register":
        if seen["entry_sha256"] is None:
            return RollbackDecision(True, (), (), ())
        if seen["entry_sha256"] != plan.entry_sha256:
            blockers.append("OWNERSHIP MISMATCH: entry changed since write")
        else:
            return RollbackDecision(True, (), (plan.entry_relative,), ())
    else:
        blockers.append("NO UNWIND FOR DRY RUN")
    return RollbackDecision(False, (), (), tuple(blockers))
