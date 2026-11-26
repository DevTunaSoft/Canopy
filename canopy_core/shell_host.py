"""Prototype transactional presentation lifecycle for explicitly trusted host adapters.

Important limits:
- Factories are registered *in host code*. NEVER import or instantiate
  classes/QML from Shell Pack metadata, paths, archives or downloaded plugins.
- This is an in-process orchestration primitive tested with dummy adapters.
  It does NOT integrate with Qt, compositor/window state, Mint sessions,
  signatures, sandboxing, or a live desktop switcher.
"""

from dataclasses import dataclass
from threading import Lock
from typing import Callable, FrozenSet, Mapping, Optional, Protocol

from .host_events import CAPABILITIES_TOPIC
from .capabilities import (
    CapabilityError, describe as _describe_capability,
    load as _load_capability, names as _capability_names,
)
from .registry import PackScan
from .window_focus_adapter import WindowFocusAdapter, issue_host_authority


class Presentation(Protocol):
    """Methods implemented by the host's reviewed, trusted UI adapter."""

    def prepare(self) -> None: ...
    def activate(self) -> None: ...
    def deactivate(self) -> None: ...
    def dispose(self) -> None: ...


class SwitchBusy(RuntimeError):
    """A transition or shutdown is already in progress."""


@dataclass(frozen=True)
class SwitchResult:
    from_id: Optional[str]
    to_id: Optional[str]
    status: str
    active_id: Optional[str]
    recovered: bool
    note: str = ""

    @property
    def success(self) -> bool:
        return self.status in ("SWITCHED", "ALREADY_ACTIVE", "STOPPED")


@dataclass(frozen=True)
class HostAuditSnapshot:
    """Frozen, read-only point-in-time view of host coordination state.

    Reports only bookkeeping the host already keeps in process: the active
    presentation id, the recovery flag, the host-allowed catalog capability
    names and decision counts from the host's most recently issued focus
    adapter. Taking a snapshot imports no feature module, starts no lifecycle
    action, performs no I/O and mutates no host or adapter state.

    The adapter reference is a single bounded slot (replaced on each
    :meth:`ShellHost.make_focus_adapter` call), mirroring the single-active
    presentation model; counts therefore describe the latest adapter only.
    This is in-process diagnostics, not proof of a running shell or a window
    action.
    """
    active_pack_id: Optional[str]
    needs_recovery: bool
    capability_names: tuple
    focus_decision_count: int
    focus_rejection_count: int
    focus_replay_count: int


class ShellHost:
    """Single-active-presentation state coordinator (not a Qt runtime loader).

    The factory map is explicitly supplied by trusted application code.
    Every target must also exist in the validated, metadata-only PackScan and
    request no host capabilities outside the provided allowlist.
    """

    def __init__(
        self,
        catalog: PackScan,
        factories: Mapping[str, Callable[[], Presentation]],
        host_capabilities: FrozenSet[str],
    ):
        if not isinstance(host_capabilities, frozenset):
            raise TypeError("host_capabilities must be a frozenset")
        if not isinstance(catalog, PackScan):
            raise TypeError("catalog must be a validated PackScan")
        for pack_id, factory in factories.items():
            if not isinstance(pack_id, str) or not callable(factory):
                raise TypeError("trusted factories need string IDs and callables")
        self._catalog = catalog
        self._factories = dict(factories)
        self._capabilities = host_capabilities
        self._lock = Lock()
        self._active_id: Optional[str] = None
        self._active_view: Optional[Presentation] = None
        self._needs_recovery = False
        # Opaque authority minted in trusted host code; pack metadata can
        # never construct a focus adapter.
        self._focus_authority = issue_host_authority()
        # Single bounded slot for the most recently issued decision-only
        # focus adapter; replaced on each make_focus_adapter call.
        self._focus_adapter: Optional[WindowFocusAdapter] = None

    @property
    def active_id(self) -> Optional[str]:
        return self._active_id

    @property
    def needs_recovery(self) -> bool:
        return self._needs_recovery

    def available_capabilities(self) -> tuple:
        """Static catalog names explicitly allowed by this host.

        The host capability allowlist supplied at construction gates every
        return value. Discovery imports no feature module and changes no
        presentation state.
        """
        return tuple(name for name in _capability_names()
                     if name in self._capabilities)

    def describe_capability(self, name: str):
        """Return the immutable descriptor for one host-allowed capability."""
        if not isinstance(name, str) or name not in self._capabilities:
            raise CapabilityError("capability not allowed by this host")
        return _describe_capability(name)

    def load_capability(self, name: str):
        """Lazily load one host-allowed pure capability callable."""
        descriptor = self.describe_capability(name)
        if descriptor.visual:
            raise CapabilityError("visual capabilities are not loadable here")
        return _load_capability(name)

    def make_focus_adapter(self, authorize):
        """Create a decision-only focus advisory owned by this host.

        ``authorize`` is the host's explicit approve callback. The adapter
        never receives an activation backend, so it can report a decision but
        cannot change a window, launch an app or query the compositor.
        """
        adapter = WindowFocusAdapter(self._focus_authority, authorize)
        # Replace the single bounded slot; older adapters are no longer
        # referenced by the host and become collectable by the caller.
        self._focus_adapter = adapter
        return adapter

    def audit_snapshot(self) -> HostAuditSnapshot:
        """Return one frozen, side-effect-free view of host coordination state.

        This is a non-locking best-effort point-in-time read, consistent with
        the ``active_id`` and ``needs_recovery`` properties. It imports no
        feature module (``available_capabilities`` is a static catalog lookup)
        and neither advances nor clears any adapter decision bookkeeping.
        """
        adapter = self._focus_adapter
        return HostAuditSnapshot(
            active_pack_id=self._active_id,
            needs_recovery=self._needs_recovery,
            capability_names=self.available_capabilities(),
            focus_decision_count=adapter.decision_count if adapter is not None else 0,
            focus_rejection_count=adapter.rejection_count if adapter is not None else 0,
            focus_replay_count=adapter.replay_count if adapter is not None else 0,
        )

    def publish_capability_report(self, records, bus):
        """Emit one bounded capability report on explicit host request only.

        No subscription is created and no reference is retained: the caller
        owns the bus lifecycle. There is no timer, polling or periodic call.
        The payload is built solely from the validated frozen report.
        """
        if not callable(getattr(bus, "emit", None)):
            raise CapabilityReportError("event bus does not support emit")
        report = self.capability_report(records)
        return bus.emit(CAPABILITIES_TOPIC, capability_event_payload(report))

    def capability_report(self, records):
        """Compose four already-produced read-only records into one report.

        ``records`` carries the ``to_dict``/``as_dict`` output of the merged
        reliability, readiness, security and launch-outcome modules. This
        method performs no I/O, launches nothing, imports no feature module and
        changes no host or adapter state; it only pins the records structurally
        and copies fixed tokens into a frozen report.
        """
        return _compose_capability_report(
            records, self._active_id is not None, self._needs_recovery)

    @staticmethod
    def _attempt(view: Presentation, method: str) -> Optional[str]:
        try:
            getattr(view, method)()
            return None
        except Exception as exc:
            # Do not leak exception messages; callbacks may carry secrets.
            return type(exc).__name__

    def _check_target(self, pack_id: str) -> Optional[str]:
        if not isinstance(pack_id, str):
            return "invalid pack ID"
        entry = self._catalog.get(pack_id)
        if entry is None:
            return "pack ID not in validated metadata catalog"
        if not entry.capabilities.issubset(self._capabilities):
            return "capability requirements unsupported"
        if pack_id not in self._factories:
            return "no explicitly trusted host adapter registered"
        return None

    def switch(self, pack_id: str) -> SwitchResult:
        if not self._lock.acquire(blocking=False):
            raise SwitchBusy("another presentation transition is running")
        try:
            return self._switch_locked(pack_id)
        finally:
            self._lock.release()

    def _switch_locked(self, pack_id: str) -> SwitchResult:
        previous_id = self._active_id
        if self._needs_recovery:
            return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                previous_id, False)
        reason = self._check_target(pack_id)
        if reason:
            return SwitchResult(previous_id, pack_id, "REJECTED",
                                previous_id, bool(previous_id), reason)
        if previous_id == pack_id:
            return SwitchResult(previous_id, pack_id, "ALREADY_ACTIVE",
                                previous_id, True)

        # Factory is invoked only from an explicit, trusted host-side map.
        try:
            candidate = self._factories[pack_id]()
            if candidate is None:
                raise ValueError("factory returned no adapter")
        except Exception as exc:
            return SwitchResult(previous_id, pack_id, "FACTORY_FAILED",
                                previous_id, bool(previous_id), type(exc).__name__)

        if candidate is self._active_view:
            return SwitchResult(previous_id, pack_id, "FACTORY_FAILED",
                                previous_id, True,
                                "trusted adapter factory reused the active instance")

        prepared_error = self._attempt(candidate, "prepare")
        if prepared_error:
            cleanup_error = self._attempt(candidate, "dispose")
            note = f"prepare: {prepared_error}"
            if cleanup_error:
                # Candidate cleanup did not complete. An old presentation may
                # still be active, but a second presenter could hold resources.
                # Do not allow more switches before an out-of-band recovery.
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                    previous_id, False,
                                    note + f"; cleanup: {cleanup_error}")
            return SwitchResult(previous_id, pack_id, "PREPARE_FAILED",
                                previous_id, bool(previous_id), note)

        old_view = self._active_view
        if old_view is not None:
            error = self._attempt(old_view, "deactivate")
            if error:
                cleanup_error = self._attempt(candidate, "dispose")
                recovered_error = self._attempt(old_view, "activate")
                if recovered_error or cleanup_error:
                    # A failed dispose cannot be interpreted as rollback,
                    # even when the old presentation was reactivated.
                    self._needs_recovery = True
                    return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                        previous_id, False,
                                        "deactivation, cleanup or restoration incomplete")
                return SwitchResult(previous_id, pack_id, "DEACTIVATE_FAILED",
                                    previous_id, True, error)

        activated_error = self._attempt(candidate, "activate")
        if activated_error:
            # Candidate activation may have partially completed. Never
            # reactivate the old view until candidate deactivation succeeded.
            candidate_off_error = self._attempt(candidate, "deactivate")
            if candidate_off_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                    previous_id, False,
                                    "candidate activation and deactivation failed")
            cleanup_error = self._attempt(candidate, "dispose")
            if old_view is not None:
                old_restore_error = self._attempt(old_view, "activate")
                if old_restore_error:
                    self._needs_recovery = True
                    return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                        previous_id, False,
                                        "old presentation restore failed")
            if cleanup_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "RECOVERY_REQUIRED",
                                    previous_id, False,
                                    "candidate activation failed and cleanup incomplete")
            return SwitchResult(previous_id, pack_id, "ACTIVATE_FAILED",
                                previous_id, True, activated_error)

        self._active_view = candidate
        self._active_id = pack_id
        if old_view is not None:
            dispose_error = self._attempt(old_view, "dispose")
            if dispose_error:
                # New presentation is active, but old resources might remain.
                # Freeze further transitions rather than accumulate leaks.
                self._needs_recovery = True
                return SwitchResult(previous_id, pack_id, "CLEANUP_FAILED",
                                    pack_id, False, "old adapter dispose failed")
        return SwitchResult(previous_id, pack_id, "SWITCHED", pack_id, True)

    def stop(self) -> SwitchResult:
        if not self._lock.acquire(blocking=False):
            raise SwitchBusy("another presentation transition is running")
        try:
            previous_id = self._active_id
            if self._needs_recovery:
                # Shutdown is terminal even when an earlier failure froze
                # transitions. Release the last focus adapter and its
                # host-supplied authorize callback here too; diagnostics keep
                # the recovery flag and counts, not a live adapter.
                self._focus_adapter = None
                return SwitchResult(previous_id, None, "RECOVERY_REQUIRED",
                                    previous_id, False)
            if self._active_view is None:
                # Shutdown is terminal: release the last focus adapter (and
                # the host-supplied authorize callback it holds) even though
                # the host object itself may stay alive for diagnostics.
                self._focus_adapter = None
                return SwitchResult(None, None, "STOPPED", None, True)
            off_error = self._attempt(self._active_view, "deactivate")
            if off_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, None, "RECOVERY_REQUIRED",
                                    previous_id, False, "could not deactivate active UI")
            old_view = self._active_view
            self._active_view = None
            self._active_id = None
            dispose_error = self._attempt(old_view, "dispose")
            # Release the decision-only adapter on every completed stop path,
            # including failed dispose; recovery diagnostics keep the flag.
            self._focus_adapter = None
            if dispose_error:
                self._needs_recovery = True
                return SwitchResult(previous_id, None, "CLEANUP_FAILED", None,
                                    False, "adapter dispose failed")
            return SwitchResult(previous_id, None, "STOPPED", None, True)
        finally:
            self._lock.release()


# Bounded, read-only composition of already-merged pure snapshot records.
CAPABILITY_REPORT_SCHEMA = 1
# Hard cap: eight bounded records, no growth path for caller-supplied records.
CAPABILITY_COMPONENTS = ("reliability", "readiness", "security", "launch",
                         "focus", "session", "recovery", "desktop")
CAPABILITY_RECORD_KEYS = frozenset(("schema",) + CAPABILITY_COMPONENTS)
RELIABILITY_RECORD_KEYS = frozenset({
    "schema", "status", "acceptance", "startup", "delivery", "switcher",
})
READINESS_RECORD_KEYS = frozenset({
    "status", "schema", "component_count", "component_tokens",
    "release_approved", "linux_mint_acceptance_proven", "owner_visual_approval",
    "desktop_session_started", "shell_running", "process_launched",
    "measurement_performed", "real_hardware_measured", "installation_attempted",
})
SECURITY_RECORD_KEYS = frozenset({
    "status", "schema", "uri_status", "privilege_status", "privilege_reason",
    "metadata_status", "metadata_capability_count", "launch_authorized",
    "process_launched", "release_approved", "linux_mint_acceptance_proven",
    "real_hardware_measured", "owner_visual_approval", "measurement_performed",
})
LAUNCH_RECORD_KEYS = frozenset({
    "status", "reason", "event_count", "relevant_count", "success_count",
    "failure_count", "retry_count", "claims",
})
FOCUS_RECORD_KEYS = frozenset({
    "schema", "status", "acceptance", "observation", "focus", "workspace",
    "switcher",
})
SESSION_RECORD_KEYS = frozenset({
    "schema", "status", "acceptance", "switcher", "workspace", "portal",
    "negotiation",
})
RECOVERY_RECORD_KEYS = frozenset({
    "schema", "status", "acceptance", "observation", "startup", "session",
    "delivery",
})
DESKTOP_RECORD_KEYS = frozenset({
    "status", "reason", "declared_count", "action_count", "argv_length",
    "claims",
})
CORE_STATUS_TOKENS = frozenset({"OK", "ATTENTION", "BLOCKED"})
LAUNCH_STATUS_TOKENS = frozenset({"SUCCEEDED", "RETRY", "GIVE_UP", "IDLE"})
DESKTOP_STATUS_TOKENS = frozenset({"READY", "DENIED"})
DESKTOP_REASON_TOKENS = frozenset({
    "ok", "invalid_input", "invalid_actions", "unapproved_action",
    "unsafe_exec", "invalid_argv", "source_disagreement",
})
DESKTOP_CLAIM_TOKENS = frozenset({
    "no_process_launched", "no_value_echo", "no_shell_metacharacters",
    "no_field_codes", "no_unapproved_action", "no_desktop_claim",
})
COMPONENT_TOKENS = (CORE_STATUS_TOKENS | LAUNCH_STATUS_TOKENS
                    | DESKTOP_STATUS_TOKENS | frozenset({
                        "READINESS_SNAPSHOT", "SNAPSHOT", "VALID", "PLAN_SNAPSHOT",
                    }))
LAUNCH_CLAIM_TOKENS = frozenset({
    "no_app_id_echo", "no_reason_text_echo", "no_process_launch", "no_io",
    "no_geometry_read", "no_visual_change",
})
MAX_COMPONENT_COUNT = 64
MAX_NESTED_ITEMS = 128
MAX_NESTED_TEXT = 256
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


CAPABILITY_NEGATIVE_CLAIMS = (
    "release=not_approved;mint=not_approved;visual=not_approved;"
    "process=not_launched;io=none;capability=not_activated;"
    "desktop=not_claimed;geometry=not_read"
)


def capability_event_payload(report):
    """Return a flat, bounded, fixed-token payload for one report."""
    if not isinstance(report, HostCapabilityReport):
        raise CapabilityReportError("event payload requires a frozen report")
    data = report.as_dict()
    codes = "|".join(data["component_tokens"])
    if len(codes.encode("utf-8", "strict")) > 512:
        raise CapabilityReportError("event component codes exceed bound")
    return {
        "status": data["status"],
        "schema": data["schema"],
        "component_count": data["component_count"],
        "component_codes": codes,
        "has_active_pack": data["has_active_pack"],
        "needs_recovery": data["needs_recovery"],
        "negative_claims": CAPABILITY_NEGATIVE_CLAIMS,
    }


class CapabilityReportError(ValueError):
    """Malformed, unbounded or unrecognized host capability record."""


@dataclass(frozen=True)
class HostCapabilityReport:
    """Frozen, value-free composition of four already-produced records."""

    schema: int
    has_active_pack: bool
    needs_recovery: bool
    component_count: int
    component_tokens: tuple

    def as_dict(self):
        """Return a fresh report with fixed negative claims."""
        if self.schema != CAPABILITY_REPORT_SCHEMA or type(self.schema) is not int:
            raise CapabilityReportError("capability report schema is unsupported")
        if type(self.has_active_pack) is not bool or type(self.needs_recovery) is not bool:
            raise CapabilityReportError("capability report flags are invalid")
        if (type(self.component_count) is not int
                or self.component_count != len(CAPABILITY_COMPONENTS)):
            raise CapabilityReportError("capability report count is invalid")
        tokens = self.component_tokens
        if (type(tokens) is not tuple or len(tokens) != len(CAPABILITY_COMPONENTS)
                or any(type(token) is not str for token in tokens)
                or tokens[0] not in CORE_STATUS_TOKENS
                or tokens[1] != "READINESS_SNAPSHOT" or tokens[2] != "SNAPSHOT"
                or tokens[3] not in LAUNCH_STATUS_TOKENS
                or tokens[4] not in CORE_STATUS_TOKENS
                or tokens[5] not in CORE_STATUS_TOKENS
                or tokens[6] not in CORE_STATUS_TOKENS
                or tokens[7] not in DESKTOP_STATUS_TOKENS):
            raise CapabilityReportError("capability report tokens are invalid")
        return {
            "status": "CAPABILITY_REPORT",
            "schema": CAPABILITY_REPORT_SCHEMA,
            "has_active_pack": self.has_active_pack,
            "needs_recovery": self.needs_recovery,
            "component_count": self.component_count,
            "component_tokens": list(tokens),
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "owner_visual_approval": False,
            "process_launched": False,
            "io_performed": False,
            "capability_activated": False,
            "desktop_session_started": False,
            "measurement_performed": False,
            "real_hardware_measured": False,
            "desktop_claim": False,
            "window_geometry_read": False,
        }


def _record(value, keys, label):
    if not isinstance(value, Mapping) or frozenset(value) != keys:
        raise CapabilityReportError(label + " record has an unexpected key set")
    return value


def _cap_token(value, allowed, label):
    # Type-check before membership so unhashable wrong types cannot leak a
    # raw TypeError past this fail-closed boundary.
    if type(value) is not str or value not in allowed:
        raise CapabilityReportError(label + " token is unsupported")
    return value


def _cap_count(value, label, maximum=MAX_COMPONENT_COUNT):
    if type(value) is not int or not 0 <= value <= maximum:
        raise CapabilityReportError(label + " count is invalid or unbounded")
    return value


def _cap_false(value, label):
    if value is not False:
        raise CapabilityReportError(label + " negative claim is not False")


def _bounded_leaf(value, label):
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        _cap_count(value, label)
        return
    if type(value) is str:
        if len(value) > MAX_NESTED_TEXT:
            raise CapabilityReportError(label + " nested text is unbounded")
        return
    if type(value) in (list, tuple):
        if len(value) > MAX_NESTED_ITEMS:
            raise CapabilityReportError(label + " nested collection is unbounded")
        for item in value:
            _bounded_leaf(item, label)
        return
    raise CapabilityReportError(label + " nested value type is unsupported")


def _bounded_view(value, keys, label):
    view = _record(value, keys, label)
    for key in keys:
        _bounded_leaf(view[key], label + " " + key)
    return view


def _compose_capability_report(records, has_active_pack, needs_recovery):
    if type(records) is not dict or frozenset(records) != CAPABILITY_RECORD_KEYS:
        raise CapabilityReportError("capability records have an unexpected key set")
    _cap_count(records["schema"], "record schema", 1)
    if records["schema"] != 1:
        raise CapabilityReportError("capability record schema is unsupported")

    reliability = _record(records["reliability"], RELIABILITY_RECORD_KEYS,
                          "reliability")
    _cap_count(reliability["schema"], "reliability schema", 1)
    reliability_token = _cap_token(
        reliability["status"], CORE_STATUS_TOKENS, "reliability status")
    _cap_token(reliability["acceptance"], frozenset({"NOT_ESTABLISHED"}),
               "reliability acceptance")
    _bounded_view(reliability["startup"], STARTUP_KEYS, "reliability startup")
    _bounded_view(reliability["delivery"], DELIVERY_KEYS, "reliability delivery")
    _bounded_view(reliability["switcher"], SWITCHER_KEYS, "reliability switcher")

    readiness = _record(records["readiness"], READINESS_RECORD_KEYS, "readiness")
    _cap_token(readiness["status"], frozenset({"READINESS_SNAPSHOT"}),
               "readiness status")
    _cap_count(readiness["schema"], "readiness schema", 1)
    tokens = readiness["component_tokens"]
    if (type(tokens) not in (list, tuple) or len(tokens) > 8
            or any(_cap_token(token, COMPONENT_TOKENS, "readiness component") is None
                   for token in tokens)):
        raise CapabilityReportError("readiness component tokens are invalid")
    for key in READINESS_RECORD_KEYS - {"status", "schema", "component_count",
                                        "component_tokens"}:
        _cap_false(readiness[key], "readiness " + key)

    security = _record(records["security"], SECURITY_RECORD_KEYS, "security")
    _cap_token(security["status"], frozenset({"SNAPSHOT"}), "security status")
    _cap_count(security["schema"], "security schema", 1)
    _cap_token(security["uri_status"], frozenset({"PERMITTED", "REJECTED"}),
               "security uri status")
    _cap_token(security["privilege_status"], frozenset({"ALLOWED", "DENIED"}),
               "security privilege status")
    _cap_count(security["metadata_capability_count"], "capability count",
               MAX_COMPONENT_COUNT)
    for key in ("launch_authorized", "process_launched", "release_approved",
                "linux_mint_acceptance_proven", "real_hardware_measured",
                "owner_visual_approval", "measurement_performed"):
        _cap_false(security[key], "security " + key)

    launch = _record(records["launch"], LAUNCH_RECORD_KEYS, "launch")
    launch_token = _cap_token(
        launch["status"], LAUNCH_STATUS_TOKENS, "launch status")
    _cap_token(launch["reason"], frozenset({
        "ok", "no_events", "retry_budget", "retry_exhausted"}), "launch reason")
    for key in ("event_count", "relevant_count", "success_count",
                "failure_count", "retry_count"):
        _cap_count(launch[key], "launch " + key)
    claims = launch["claims"]
    if (type(claims) not in (list, tuple) or len(claims) > 8
            or any(_cap_token(claim, LAUNCH_CLAIM_TOKENS, "launch claim") is None
                   for claim in claims)):
        raise CapabilityReportError("launch claims are invalid")

    focus = _record(records["focus"], FOCUS_RECORD_KEYS, "focus")
    _cap_count(focus["schema"], "focus schema", 1)
    focus_token = _cap_token(focus["status"], CORE_STATUS_TOKENS, "focus status")
    _cap_token(focus["acceptance"], frozenset({"NOT_ESTABLISHED"}),
               "focus acceptance")
    _cap_token(focus["observation"], frozenset({"NOT_PERFORMED"}),
               "focus observation")
    _bounded_view(focus["focus"], frozenset({
        "live_windows", "grant_count", "decision_count", "statuses",
        "target_apps", "reasons"}), "focus detail")
    _bounded_view(focus["workspace"], frozenset({
        "workspace_count", "identifiers", "problem_count", "problem_reasons"}),
        "focus workspace")
    _bounded_view(focus["switcher"], SWITCHER_KEYS, "focus switcher")

    session = _record(records["session"], SESSION_RECORD_KEYS, "session")
    _cap_count(session["schema"], "session schema", 1)
    session_token = _cap_token(
        session["status"], CORE_STATUS_TOKENS, "session status")
    _cap_token(session["acceptance"], frozenset({"NOT_ESTABLISHED"}),
               "session acceptance")
    _bounded_view(session["switcher"], SWITCHER_KEYS, "session switcher")
    _bounded_view(session["workspace"], frozenset({
        "workspace_count", "identifiers", "problem_count", "problem_reasons"}),
        "session workspace")
    _bounded_view(session["portal"], frozenset({
        "capability_count", "denied", "missing", "session_type",
        "unknown_permission", "usable", "wayland", "window_enumeration"}),
        "session portal")
    _bounded_view(session["negotiation"], frozenset({
        "backend", "granted", "status", "supported"}), "session negotiation")

    recovery = _record(records["recovery"], RECOVERY_RECORD_KEYS, "recovery")
    _cap_count(recovery["schema"], "recovery schema", 1)
    recovery_token = _cap_token(
        recovery["status"], CORE_STATUS_TOKENS, "recovery status")
    _cap_token(recovery["acceptance"], frozenset({"NOT_ESTABLISHED"}),
               "recovery acceptance")
    _cap_token(recovery["observation"], frozenset({"NOT_PERFORMED"}),
               "recovery observation")
    _bounded_view(recovery["startup"], STARTUP_KEYS, "recovery startup")
    _bounded_view(recovery["session"], frozenset({
        "accepted", "label", "locked", "recent_statuses", "suspended"}),
        "recovery session")
    _bounded_view(recovery["delivery"], DELIVERY_KEYS, "recovery delivery")

    desktop = _record(records["desktop"], DESKTOP_RECORD_KEYS, "desktop")
    desktop_token = _cap_token(
        desktop["status"], DESKTOP_STATUS_TOKENS, "desktop status")
    _cap_token(desktop["reason"], DESKTOP_REASON_TOKENS, "desktop reason")
    for key in ("declared_count", "action_count", "argv_length"):
        _cap_count(desktop[key], "desktop " + key)
    desktop_claims = desktop["claims"]
    if (type(desktop_claims) not in (list, tuple) or len(desktop_claims) > 6
            or any(_cap_token(claim, DESKTOP_CLAIM_TOKENS,
                              "desktop claim") is None
                   for claim in desktop_claims)):
        raise CapabilityReportError("desktop claims are invalid")

    if type(has_active_pack) is not bool or type(needs_recovery) is not bool:
        raise CapabilityReportError("host state flags are invalid")
    return HostCapabilityReport(
        schema=CAPABILITY_REPORT_SCHEMA,
        has_active_pack=has_active_pack,
        needs_recovery=needs_recovery,
        component_count=len(CAPABILITY_COMPONENTS),
        component_tokens=(reliability_token, "READINESS_SNAPSHOT", "SNAPSHOT",
                          launch_token, focus_token, session_token,
                          recovery_token, desktop_token),
    )

