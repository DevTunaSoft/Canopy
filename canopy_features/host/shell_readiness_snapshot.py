"""Pure, immutable composition of offline host snapshot records.

This module composes the read-only records produced by five already-tested
offline snapshots into one bounded, deterministic readiness record:

``security_decision_snapshot``, ``host_reliability_snapshot``,
``performance_snapshot``, ``installer_plan_snapshot`` and
``window_session_snapshot``.

It composes *records*, not modules: no producer is imported and the
installer record may be supplied by a caller whose producer has not landed
yet. Every record is structurally pinned (exact key sets, schema, fixed
status tokens, bounded counts and values) before any token is copied. The
performance record is additionally checked by the already-merged offline
artifact validator. Only fixed tokens and a component count reach the output.

This is NOT proof that a shell is running, that a desktop session started,
that a release or Linux Mint guest was accepted, that an owner approved
visuals, or that any measurement was performed on real hardware. Those
negative claims are hardcoded. Nothing here reads a file, clock, environment,
socket or process; nothing launches, executes, imports Qt or touches visuals.
"""
from collections.abc import Mapping
from dataclasses import dataclass

from tools.qa import perf_snapshot_artifact_validator as perf_validator

SCHEMA = 1
COMPONENTS = ("security", "reliability", "performance", "installer", "window")
WRAPPER_KEYS = frozenset(("schema",) + COMPONENTS)

MAX_COUNT = 100_000
MAX_TEXT = 4_096
MAX_ITEMS = 128

CORE_STATUSES = frozenset({"OK", "ATTENTION", "BLOCKED"})
NEGATIVE_CLAIMS = frozenset({"NOT_ESTABLISHED"})
PRIVILEGE_REASONS = frozenset({
    "allowed", "empty-action", "invalid-action", "oversized-action",
    "inherited-root", "elevation-command", "system-command",
})
COMPONENT_TOKENS = frozenset({
    "SNAPSHOT", "OK", "ATTENTION", "BLOCKED", "VALID", "PLAN_SNAPSHOT",
})

SECURITY_KEYS = frozenset({
    "status", "schema", "uri_status", "privilege_status", "privilege_reason",
    "metadata_status", "metadata_capability_count", "launch_authorized",
    "process_launched", "release_approved", "linux_mint_acceptance_proven",
    "real_hardware_measured", "owner_visual_approval", "measurement_performed",
})
SECURITY_NEGATIVES = frozenset({
    "launch_authorized", "process_launched", "release_approved",
    "linux_mint_acceptance_proven", "real_hardware_measured",
    "owner_visual_approval", "measurement_performed",
})
INSTALLER_KEYS = frozenset({
    "status", "schema", "icon_status", "xdg_status", "ownership_status",
    "ownership_file_count", "session_status", "filesystem_verified",
    "binary_verified", "uninstall_executed", "session_registered",
    "package_installed", "release_approved", "linux_mint_acceptance_proven",
    "owner_visual_approval",
})
INSTALLER_NEGATIVES = frozenset({
    "filesystem_verified", "binary_verified", "uninstall_executed",
    "session_registered", "package_installed", "release_approved",
    "linux_mint_acceptance_proven", "owner_visual_approval",
})
RELIABILITY_KEYS = frozenset({
    "schema", "status", "acceptance", "startup", "delivery", "switcher",
})
WINDOW_KEYS = frozenset({
    "schema", "status", "acceptance", "switcher", "workspace", "portal",
    "negotiation",
})
STARTUP_KEYS = frozenset({
    "action", "safe_to_start", "needs_rollback", "completed_count",
    "unwind_count", "reason",
})
DELIVERY_KEYS = frozenset({
    "sent", "received", "delivered", "duplicates", "reordered", "gaps",
    "missed", "dropped", "rejected", "notice_count", "last_policy",
})
SWITCHER_KEYS = frozenset({
    "active", "current", "selected", "window_count", "order",
})
WORKSPACE_KEYS = frozenset({
    "workspace_count", "identifiers", "problem_count", "problem_reasons",
})
PORTAL_KEYS = frozenset({
    "session_type", "wayland", "window_enumeration", "capability_count",
    "usable", "denied", "missing", "unknown_permission",
})
NEGOTIATION_KEYS = frozenset({
    "backend", "status", "granted", "supported",
})


class ReadinessError(ValueError):
    """Malformed, unbounded or unrecognized host readiness input."""


def _mapping(value, keys, label):
    if not isinstance(value, Mapping) or frozenset(value) != keys:
        raise ReadinessError(label + " has an unexpected key set")
    return value


def _token(value, allowed, label):
    # Type-check before membership: unhashable wrong types must not leak a
    # raw TypeError past this fail-closed boundary (item 11 contract class).
    if type(value) is not str or value not in allowed:
        raise ReadinessError(label + " token is unsupported")
    return value


def _count(value, label, maximum=MAX_COUNT):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ReadinessError(label + " count is invalid or unbounded")
    return value


def _false(value, label):
    if value is not False:
        raise ReadinessError(label + " negative claim is not False")


def _bounded_value(value, label):
    """Recursively bound a leaf value from a nested snapshot view."""
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        _count(value, label)
        return
    if type(value) is str:
        if len(value) > MAX_TEXT:
            raise ReadinessError(label + " text is unbounded")
        return
    if type(value) in (list, tuple):
        if len(value) > MAX_ITEMS:
            raise ReadinessError(label + " collection is unbounded")
        for item in value:
            _bounded_value(item, label)
        return
    raise ReadinessError(label + " has an unsupported value type")


def _check_view(value, keys, label):
    view = _mapping(value, keys, label)
    for key in keys:
        _bounded_value(view[key], label + " " + key)
    return view


def _security(record):
    r = _mapping(record, SECURITY_KEYS, "security snapshot")
    _token(r["status"], frozenset({"SNAPSHOT"}), "security status")
    _count(r["schema"], "security schema", 1)
    if r["schema"] != 1:
        raise ReadinessError("security schema is unsupported")
    _token(r["uri_status"], frozenset({"PERMITTED", "REJECTED"}), "uri status")
    _token(r["privilege_status"], frozenset({"ALLOWED", "DENIED"}), "privilege status")
    _token(r["privilege_reason"], PRIVILEGE_REASONS, "privilege reason")
    _token(r["metadata_status"], frozenset({"SAFE", "REJECTED"}), "metadata status")
    _count(r["metadata_capability_count"], "capability count", MAX_ITEMS)
    for key in SECURITY_NEGATIVES:
        _false(r[key], "security " + key)
    return "SNAPSHOT"


def _reliability(record):
    r = _mapping(record, RELIABILITY_KEYS, "reliability snapshot")
    _count(r["schema"], "reliability schema", 1)
    if r["schema"] != 1:
        raise ReadinessError("reliability schema is unsupported")
    status = _token(r["status"], CORE_STATUSES, "reliability status")
    _token(r["acceptance"], NEGATIVE_CLAIMS, "reliability acceptance")
    _check_view(r["startup"], STARTUP_KEYS, "reliability startup")
    _check_view(r["delivery"], DELIVERY_KEYS, "reliability delivery")
    _check_view(r["switcher"], SWITCHER_KEYS, "reliability switcher")
    return status


def _performance(record):
    try:
        report = perf_validator.validate(record)
    except perf_validator.ArtifactError as exc:
        raise ReadinessError("performance record rejected") from exc
    return _token(report["status"], frozenset({"VALID"}), "performance status")


def _installer(record):
    r = _mapping(record, INSTALLER_KEYS, "installer snapshot")
    _token(r["status"], frozenset({"PLAN_SNAPSHOT"}), "installer status")
    _count(r["schema"], "installer schema", 1)
    if r["schema"] != 1:
        raise ReadinessError("installer schema is unsupported")
    _token(r["icon_status"],
           frozenset({"AVAILABLE", "UNAVAILABLE", "REFUSED", "INVALID"}),
           "icon status")
    _token(r["xdg_status"],
           frozenset({"WITHIN_HOME", "OUTSIDE_HOME", "INVALID"}), "xdg status")
    _token(r["ownership_status"], frozenset({"VALID", "INVALID"}), "ownership status")
    _token(r["session_status"], frozenset({"VALID", "INVALID"}), "session status")
    _count(r["ownership_file_count"], "ownership file count", MAX_COUNT)
    for key in INSTALLER_NEGATIVES:
        _false(r[key], "installer " + key)
    return "PLAN_SNAPSHOT"


def _window(record):
    r = _mapping(record, WINDOW_KEYS, "window snapshot")
    _count(r["schema"], "window schema", 1)
    if r["schema"] != 1:
        raise ReadinessError("window schema is unsupported")
    status = _token(r["status"], CORE_STATUSES, "window status")
    _token(r["acceptance"], NEGATIVE_CLAIMS, "window acceptance")
    _check_view(r["switcher"], SWITCHER_KEYS, "window switcher")
    _check_view(r["workspace"], WORKSPACE_KEYS, "window workspace")
    _check_view(r["portal"], PORTAL_KEYS, "window portal")
    _check_view(r["negotiation"], NEGOTIATION_KEYS, "window negotiation")
    return status


_VALIDATORS = {
    "security": _security,
    "reliability": _reliability,
    "performance": _performance,
    "installer": _installer,
    "window": _window,
}


@dataclass(frozen=True)
class ShellReadinessSnapshot:
    """Frozen, value-free readiness record of five composed snapshot tokens."""

    schema: int
    component_count: int
    component_tokens: tuple

    def as_dict(self):
        """Return a fresh copy with fixed negative claims.""" 
        _count(self.schema, "schema", 1)
        if self.schema != 1:
            raise ReadinessError("readiness schema is unsupported")
        _count(self.component_count, "component count", len(COMPONENTS))
        tokens = self.component_tokens
        if (type(tokens) is not tuple or len(tokens) != len(COMPONENTS)
                or any(_token(token, COMPONENT_TOKENS, "component") is None
                       for token in tokens)):
            raise ReadinessError("component tokens are invalid")
        return {
            "status": "READINESS_SNAPSHOT",
            "schema": SCHEMA,
            "component_count": len(COMPONENTS),
            "component_tokens": list(tokens),
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "owner_visual_approval": False,
            "desktop_session_started": False,
            "shell_running": False,
            "process_launched": False,
            "measurement_performed": False,
            "real_hardware_measured": False,
            "installation_attempted": False,
        }


def compose(record):
    """Validate five snapshot records and compose one frozen readiness record."""
    if type(record) is not dict or frozenset(record) != WRAPPER_KEYS:
        raise ReadinessError("readiness wrapper has an unexpected key set")
    if type(record["schema"]) is not int or record["schema"] != SCHEMA:
        raise ReadinessError("readiness schema is unsupported")
    tokens = tuple(_VALIDATORS[name](record[name]) for name in COMPONENTS)
    return ShellReadinessSnapshot(
        schema=SCHEMA,
        component_count=len(tokens),
        component_tokens=tokens,
    )
