"""Bounded application-process lifecycle events recorded from explicit observations.

Trusted host code supplies each observation together with a monotonic timestamp.
This module never starts, inspects or signals a process; reads a clock; polls;
opens a socket; creates a thread; or loads a Shell Pack. It is deterministic and
testable offline on Windows and Linux without a desktop session.

``canopy_core.host_events`` is the project's synchronous event bus with a fixed
topic allowlist and no process semantics. This is not a second bus: it is a
bounded immutable history plus PID-incarnation and crash-loop state. A future
reviewed Qt/session adapter must translate these events onto the host bus; that
integration is not part of this module.

Limits: one tracked primary process per application ID, fixed-capacity history
and bookkeeping, no automatic restart policy, and no claim of observing a real
desktop process.
"""

from collections import OrderedDict, deque
from dataclasses import dataclass
import math
import re

PROTOCOL_VERSION = 1

START = "START"
EXIT = "EXIT"
PID_REUSED = "PID_REUSED"
CRASH_LOOP = "CRASH_LOOP"
KINDS = frozenset({START, EXIT, PID_REUSED, CRASH_LOOP})

MAX_EVENTS = 256
MAX_APPS = 128
MAX_RECENT_EXITS = 16
MAX_PID = (1 << 22) - 1  # above Linux 32-bit pid_max, below signed 32-bit limit
MAX_EXIT_CODE = 255
MAX_CRASH_WINDOW = 86_400
MAX_CRASH_THRESHOLD = 16

DEFAULT_MAX_EVENTS = 128
DEFAULT_MAX_APPS = 64
DEFAULT_CRASH_WINDOW = 60
DEFAULT_CRASH_THRESHOLD = 3

APP_ID = re.compile(r"[a-z][a-z0-9_.-]{0,47}\Z")


class ProcessEventError(ValueError):
    """Invalid observation, caller bound, or use of a closed tracker."""


@dataclass(frozen=True)
class ProcessEvent:
    """Immutable lifecycle record. All fields are scalar and log-safe."""

    sequence: int
    kind: str
    app_id: str
    pid: int
    generation: int
    observed_at: float
    exit_code: int = 0


@dataclass(frozen=True)
class _Incarnation:
    app_id: str
    pid: int
    generation: int


def _check_app_id(app_id):
    if type(app_id) is not str or not APP_ID.fullmatch(app_id):
        raise ProcessEventError("invalid application ID")


def _check_pid(pid):
    if type(pid) is not int or not 1 <= pid <= MAX_PID:
        raise ProcessEventError("invalid process ID")


def _check_generation(generation):
    if type(generation) is not int or generation < 1:
        raise ProcessEventError("invalid incarnation generation")


def _check_exit_code(exit_code):
    if (type(exit_code) is not int
            or not -MAX_EXIT_CODE <= exit_code <= MAX_EXIT_CODE):
        raise ProcessEventError("invalid exit code")


def _bounded_int(name, value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ProcessEventError("invalid " + name + " bound")


class ProcessLifecycle:
    """Single-threaded, event-driven lifecycle tracker with bounded state.

    ``start()`` returns the incarnation ``generation`` in its event. The caller
    must pass that generation back to ``exit()``; a stale exit from a reused
    PID is then ignored instead of closing the newer process.
    """

    def __init__(self, *, max_events=DEFAULT_MAX_EVENTS,
                 max_apps=DEFAULT_MAX_APPS,
                 crash_window=DEFAULT_CRASH_WINDOW,
                 crash_threshold=DEFAULT_CRASH_THRESHOLD):
        _bounded_int("max_events", max_events, 1, MAX_EVENTS)
        _bounded_int("max_apps", max_apps, 1, MAX_APPS)
        _bounded_int("crash_window", crash_window, 0, MAX_CRASH_WINDOW)
        _bounded_int("crash_threshold", crash_threshold, 1,
                     MAX_CRASH_THRESHOLD)
        self._max_events = max_events
        self._max_apps = max_apps
        self._crash_window = crash_window
        self._crash_threshold = crash_threshold
        self._events = deque(maxlen=max_events)
        self._live_by_app = {}
        self._live_by_pid = {}
        self._recent_exits = OrderedDict()
        self._crash_looping = set()
        self._sequence = 0
        self._generation = 0
        self._last_time = None
        self._closed = False

    def _ready(self):
        if self._closed:
            raise ProcessEventError("lifecycle tracker is closed")

    def _check_time(self, observed_at):
        if (type(observed_at) not in (int, float)
                or not math.isfinite(observed_at) or observed_at < 0):
            raise ProcessEventError("invalid observation time")
        if self._last_time is not None and observed_at < self._last_time:
            raise ProcessEventError("observation time moved backwards")

    def _emit(self, kind, app_id, pid, generation, observed_at, exit_code=0):
        self._sequence += 1
        event = ProcessEvent(self._sequence, kind, app_id, pid, generation,
                             observed_at, exit_code)
        self._events.append(event)
        return event

    def _forget(self, incarnation):
        if self._live_by_app.get(incarnation.app_id) is incarnation:
            del self._live_by_app[incarnation.app_id]
        if self._live_by_pid.get(incarnation.pid) is incarnation:
            del self._live_by_pid[incarnation.pid]

    def start(self, app_id, pid, observed_at):
        """Record a process start; force-close a live PID that was reused."""
        self._ready()
        _check_app_id(app_id)
        _check_pid(pid)
        self._check_time(observed_at)
        if (app_id not in self._live_by_app
                and len(self._live_by_app) >= self._max_apps):
            raise ProcessEventError("application limit reached")

        emitted = []
        seen = set()
        for live in (self._live_by_app.get(app_id), self._live_by_pid.get(pid)):
            if live is None or live in seen:
                continue
            seen.add(live)
            emitted.append(self._emit(PID_REUSED, live.app_id, live.pid,
                                      live.generation, observed_at))
            self._forget(live)

        self._generation += 1
        generation = self._generation
        incarnation = _Incarnation(app_id, pid, generation)
        self._live_by_app[app_id] = incarnation
        self._live_by_pid[pid] = incarnation
        self._last_time = observed_at
        emitted.append(self._emit(START, app_id, pid, generation, observed_at))
        return tuple(emitted)

    def exit(self, app_id, pid, generation, observed_at, exit_code=0):
        """Record an exit. Wrong generation means a stale exit: ignore it."""
        self._ready()
        _check_app_id(app_id)
        _check_pid(pid)
        _check_generation(generation)
        _check_exit_code(exit_code)
        self._check_time(observed_at)
        live = self._live_by_pid.get(pid)
        if (live is None or live.app_id != app_id
                or live.generation != generation):
            return ()

        self._last_time = observed_at
        self._forget(live)
        emitted = [self._emit(EXIT, app_id, pid, generation, observed_at,
                              exit_code)]
        if exit_code == 0:
            self._recent_exits.pop(app_id, None)
            self._crash_looping.discard(app_id)
            self._crash_looping.intersection_update(self._recent_exits)
            return tuple(emitted)

        if app_id not in self._recent_exits:
            if len(self._recent_exits) >= self._max_apps:
                evicted, _ = self._recent_exits.popitem(last=False)
                self._crash_looping.discard(evicted)
            self._recent_exits[app_id] = deque(maxlen=MAX_RECENT_EXITS)
        recent = self._recent_exits[app_id]
        self._recent_exits.move_to_end(app_id)
        recent.append(observed_at)
        while recent and observed_at - recent[0] > self._crash_window:
            recent.popleft()
        if (len(recent) >= self._crash_threshold
                and app_id not in self._crash_looping):
            self._crash_looping.add(app_id)
            emitted.append(self._emit(CRASH_LOOP, app_id, pid, generation,
                                      observed_at, exit_code))
        return tuple(emitted)

    def events(self):
        """Bounded immutable event history, oldest first."""
        return tuple(self._events)

    def live_generation(self, app_id):
        """Current incarnation generation, or None when not running."""
        _check_app_id(app_id)
        live = self._live_by_app.get(app_id)
        return None if live is None else live.generation

    def is_crash_looping(self, app_id):
        _check_app_id(app_id)
        return app_id in self._crash_looping

    def clear_crash_state(self, app_id):
        """Re-arm crash detection after a reviewed backoff or operator action."""
        self._ready()
        _check_app_id(app_id)
        self._recent_exits.pop(app_id, None)
        self._crash_looping.discard(app_id)

    def reset(self):
        """Drop all history and state; keep configuration and usable status."""
        self._ready()
        self._events.clear()
        self._live_by_app.clear()
        self._live_by_pid.clear()
        self._recent_exits.clear()
        self._crash_looping.clear()
        self._sequence = 0
        self._last_time = None

    def close(self):
        """Fail-closed cleanup: release all references, reject later use."""
        if self._closed:
            return
        self.reset()
        self._closed = True

    @property
    def event_count(self):
        return len(self._events)

    @property
    def closed(self):
        return self._closed
