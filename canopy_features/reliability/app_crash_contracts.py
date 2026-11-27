"""Bounded application crash contracts over the existing host event bus.

The only signal source is ``canopy_core.host_events.HostEvents`` protocol v2.
This module adds no event topic, version, callback, thread, timer, process or
I/O. It records caller-declared crash signals, isolates the named application
and exposes deterministic user-facing feedback codes. It never launches,
signals or kills a process and never echoes application identifiers, exit
codes or raw event text into a snapshot.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
    HostEvents,
    HostEventError,
)

__all__ = [
    "CrashContractError",
    "CleanupResult",
    "Feedback",
    "AppCrashSnapshot",
    "AppCrashController",
    "TrustedCrashEventSource",
    "WINDOW_TOPIC",
    "SESSION_TOPIC",
    "ALLOWED_TOPICS",
    "STATUS_READY",
    "STATUS_ISOLATED",
    "STATUS_RECOVERED",
    "FEEDBACK_READY",
    "FEEDBACK_ISOLATED",
    "FEEDBACK_RECOVERABLE",
    "FEEDBACK_UNAVAILABLE",
    "SESSION_STATE_ACTIVE",
    "SESSION_PHASE_RECOVERY",
    "CLEANABLE_RESOURCES",
    "CLEANUP_DENIED",
    "CLEANUP_DONE",
    "CLEANUP_PARTIAL",
    "MAX_CLEANUP_STEPS",
    "MAX_RECOVERIES",
    "MAX_TRACKED_APPS",
    "MAX_PID",
    "FIXED_CLAIMS",
    "NOT_ESTABLISHED",
    "PROCESS_ACTION_NOT_PERFORMED",
]

WINDOW_TOPIC = "window.state.changed"
SESSION_TOPIC = "session.state.changed"
ALLOWED_TOPICS = (WINDOW_TOPIC, SESSION_TOPIC)
if not set(ALLOWED_TOPICS).issubset(HOST_EVENT_TOPICS):
    raise RuntimeError("host event contract changed; crash adapter must be reviewed")

STATUS_READY = "READY"
STATUS_ISOLATED = "ISOLATED"
STATUS_RECOVERED = "RECOVERED"
SESSION_STATE_ACTIVE = "active"
SESSION_PHASE_RECOVERY = "recovery_granted"
# Fixed user-facing strings: no identifiers, exit codes, raw text or timing.
FEEDBACK_READY = "READY"
FEEDBACK_ISOLATED = "APP_ISOLATED"
FEEDBACK_RECOVERABLE = "APP_RECOVERABLE"
FEEDBACK_UNAVAILABLE = "STATE_UNAVAILABLE"
_FEEDBACK_TEXT = {
    FEEDBACK_READY: "Canopy is ready.",
    FEEDBACK_ISOLATED: (
        "An application stopped unexpectedly. "
        "Canopy kept the desktop available."),
    FEEDBACK_RECOVERABLE: "The application can be restarted safely.",
    FEEDBACK_UNAVAILABLE: (
        "Crash state is unavailable. Use the safe exit control."),
}
CLEANUP_DENIED = "DENIED"
CLEANUP_PARTIAL = "PARTIAL"
CLEANUP_DONE = "DONE"
CLEANABLE_RESOURCES = (
    "window", "notification", "cache", "subscription",
    "shortcut", "badge", "focus", "timer",
)
MAX_CLEANUP_STEPS = 4
MAX_RECOVERIES = 64
NOT_ESTABLISHED = "NOT_ESTABLISHED"
PROCESS_ACTION_NOT_PERFORMED = "NOT_PERFORMED"
MAX_TRACKED_APPS = 32
MAX_PID = 2 ** 31 - 1
_APP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")


def _valid_app_id(value):
    # Exact str: a subclass could override comparison and fake a match, and
    # control characters must never become a crash-isolation key.
    return type(value) is str and _APP_ID.fullmatch(value) is not None


FIXED_CLAIMS = (
    "existing_host_events_only",
    "no_app_id_echo",
    "no_io",
    "no_process_action",
    "no_visual_change",
)


class CrashContractError(ValueError):
    """Invalid event, application identifier or bound in a crash contract."""


@dataclass(frozen=True)
class Feedback:
    """One fixed, immutable user-facing status; never carries source text."""

    code: str
    message: str


@dataclass(frozen=True)
class CleanupResult:
    """One bounded cleanup step report; no source text is carried."""

    status: str
    released: int
    remaining: int
    done: bool


@dataclass(frozen=True)
class AppCrashSnapshot:
    """Immutable, no-echo view of the controller state."""

    status: str
    crash_count: int
    isolated_count: int
    cleanup_count: int
    recovery_count: int
    acceptance: str
    process_action: str
    claims: tuple

    def to_dict(self):
        return MappingProxyType({
            "status": self.status,
            "crash_count": self.crash_count,
            "isolated_count": self.isolated_count,
            "cleanup_count": self.cleanup_count,
            "recovery_count": self.recovery_count,
            "acceptance": self.acceptance,
            "process_action": self.process_action,
            "claims": self.claims,
        })


class AppCrashController:
    """Consume real host events and isolate named crashed applications."""

    __slots__ = ("_crashes", "_cleanups", "_cleanup_count", "_recoverable",
                 "_recovery_count", "_last_sequence", "_closed")

    def __init__(self):
        self._crashes = {}
        self._cleanups = {}
        self._cleanup_count = 0
        self._recoverable = set()
        self._recovery_count = 0
        self._last_sequence = 0
        self._closed = False

    def _ready(self):
        if self._closed:
            raise CrashContractError("crash controller is closed")

    def observe(self, event):
        """Apply one real HostEvent; return a fixed detection token."""
        self._ready()
        if type(event) is not HostEvent:
            raise CrashContractError("only real HostEvent instances are accepted")
        if (event.version != PROTOCOL_VERSION
                or type(event.sequence) is not int or event.sequence < 1
                or type(event.topic) is not str
                or event.topic not in ALLOWED_TOPICS):
            raise CrashContractError("unsupported host event envelope")
        if event.sequence <= self._last_sequence:
            return "STALE"
        self._last_sequence = event.sequence
        if event.topic == SESSION_TOPIC:
            payload = event.payload
            state = payload.get("state")
            phase = payload.get("phase")
            app_id = payload.get("app_id")
            if (type(state) is not str or state != SESSION_STATE_ACTIVE
                    or type(phase) is not str or phase != SESSION_PHASE_RECOVERY
                    or not _valid_app_id(app_id)):
                return "UNKNOWN"
            if app_id not in self._crashes:
                return "IGNORED"
            if self._recovery_count >= MAX_RECOVERIES:
                return "CAPACITY"
            done = self._cleanups.get(app_id, frozenset())
            if not set(CLEANABLE_RESOURCES).issubset(done):
                return "CLEANUP_PENDING"
            self._recoverable.add(app_id)
            return "RECOVERY_GRANTED"
        payload = event.payload
        state = payload.get("state")
        app_id = payload.get("app_id")
        pid = payload.get("pid")
        code = payload.get("exit_code")
        if (type(state) is not str or state not in ("crashed", "exited")
                or not _valid_app_id(app_id)
                or type(pid) is not int or not 1 <= pid <= MAX_PID
                or type(code) is not int or not -255 <= code <= 255):
            return "UNKNOWN"
        if state != "crashed" and code == 0:
            return "CLEAN_EXIT"
        if app_id in self._crashes:
            return "DUPLICATE"
        if len(self._crashes) >= MAX_TRACKED_APPS:
            return "CAPACITY"
        self._crashes[app_id] = (event.sequence, pid, code)
        return "CRASH"

    def is_isolated(self, app_id):
        self._ready()
        if type(app_id) is not str:
            raise CrashContractError("application id must be text")
        return app_id in self._crashes

    def cleanup(self, app_id, resources):
        """Release at most ``MAX_CLEANUP_STEPS`` declared resources.

        Caller names are validated before any state changes. An unknown name
        or wrong container fails closed with ``CrashContractError``; a
        non-isolated application is denied without touching any state. Repeat
        calls never release the same resource twice.
        """
        self._ready()
        if not _valid_app_id(app_id):
            raise CrashContractError("application id must be bounded text")
        if type(resources) is not tuple or len(resources) > len(CLEANABLE_RESOURCES):
            raise CrashContractError("resources must be a bounded tuple")
        for name in resources:
            if type(name) is not str or name not in CLEANABLE_RESOURCES:
                raise CrashContractError("unsupported cleanup resource")
        if app_id not in self._crashes:
            return CleanupResult(CLEANUP_DENIED, 0, len(resources), False)
        done_names = self._cleanups.setdefault(app_id, set())
        released = 0
        for name in resources:
            if released >= MAX_CLEANUP_STEPS:
                break
            if name not in done_names:
                done_names.add(name)
                released += 1
        self._cleanup_count += released
        remaining = sum(1 for name in resources if name not in done_names)
        return CleanupResult(
            CLEANUP_DONE if remaining == 0 else CLEANUP_PARTIAL,
            released, remaining, remaining == 0)

    def feedback(self, app_id):
        """Return one fixed user-facing code and string; never echo input."""
        if self._closed or not _valid_app_id(app_id):
            code = FEEDBACK_UNAVAILABLE
        elif app_id not in self._crashes:
            code = FEEDBACK_READY
        elif app_id in self._recoverable:
            code = FEEDBACK_RECOVERABLE
        else:
            code = FEEDBACK_ISOLATED
        return Feedback(code, _FEEDBACK_TEXT[code])

    def acknowledge(self, app_id):
        """Clear isolation only after a granted recovery event."""
        if (self._closed or type(app_id) is not str
                or app_id not in self._recoverable):
            return False
        self._recoverable.discard(app_id)
        self._crashes.pop(app_id, None)
        self._cleanups.pop(app_id, None)
        self._recovery_count += 1
        return True

    def snapshot(self):
        return AppCrashSnapshot(
            status=(STATUS_ISOLATED if self._crashes
                    else STATUS_RECOVERED if self._recovery_count
                    else STATUS_READY),
            crash_count=len(self._crashes),
            isolated_count=len(self._crashes),
            cleanup_count=self._cleanup_count,
            recovery_count=self._recovery_count,
            acceptance=NOT_ESTABLISHED,
            process_action=PROCESS_ACTION_NOT_PERFORMED,
            claims=FIXED_CLAIMS,
        )

    def close(self):
        self._crashes.clear()
        self._cleanups.clear()
        self._cleanup_count = 0
        self._recoverable.clear()
        self._recovery_count = 0
        self._last_sequence = 0
        self._closed = True


class TrustedCrashEventSource:
    """Host-owned event source; only trusted host code may call ``emit``."""

    __slots__ = ("_controller", "_callback", "_bus", "_tokens", "_closed")

    def __init__(self):
        self._controller = AppCrashController()
        self._callback = self._controller.observe
        self._bus = HostEvents(
            {topic: [self._callback] for topic in ALLOWED_TOPICS})
        self._tokens = tuple(self._bus.subscribe(topic, self._callback)
                             for topic in ALLOWED_TOPICS)
        self._closed = False

    @property
    def controller(self):
        return self._controller

    def emit(self, topic, payload):
        if self._closed or self._bus.closed:
            raise CrashContractError("crash event source is closed")
        return self._bus.emit(topic, payload)

    def snapshot(self):
        return self._controller.snapshot()

    def close(self):
        if self._closed:
            return
        for token in self._tokens:
            if not self._bus.closed:
                self._bus.unsubscribe(token)
        self._bus.close()
        self._controller.close()
        self._closed = True
