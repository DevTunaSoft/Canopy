"""Bounded, host-owned relaunch backoff policy for application launches.

Pure decision logic: this module starts no process, opens no socket, owns no
timer and never polls. A trusted host calls ``admit`` before a launch and
reports the outcome. Time comes from an injected monotonic clock or an
explicit ``now`` argument, so offline tests never sleep or read wall time.
State is bounded by ``max_keys`` and ``max_attempts_per_window``.
"""

from collections import OrderedDict, deque
from dataclasses import dataclass
import math
import re
import time
from threading import RLock
from typing import Optional

MAX_MAX_KEYS = 256
MAX_ATTEMPTS_LIMIT = 1024
MAX_FAILURES_LIMIT = 64

KEY = re.compile(r"[a-z][a-z0-9._-]{0,127}\Z")

ADMITTED = "ADMITTED"
RATE_LIMITED = "RATE_LIMITED"
BACKOFF = "BACKOFF"
SUSPENDED = "SUSPENDED"


class LaunchBackoffError(ValueError):
    """Invalid configuration, application key or clock input."""


@dataclass(frozen=True)
class LaunchDecision:
    """Policy answer; ``retry_after`` is 0 unless an attempt was withheld.

    ``SUSPENDED`` is terminal for that key until ``report_success`` or
    ``reset`` is called, even though its ``retry_after`` is 0.
    """

    allowed: bool
    reason: str
    retry_after: float
    failures: int


@dataclass
class _State:
    failures: int
    next_allowed: Optional[float]
    attempts: deque


def _finite_positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise LaunchBackoffError(f"invalid {name}")
    return float(value)


class AppLaunchBackoff:
    """Per-application relaunch gate with capped delay and fixed-window rate limit.

    A host sequence is: ``admit`` -> launch -> ``report_success`` /
    ``report_failure``. No callback, thread, timer or launch is owned here.
    """

    def __init__(self, *, base_delay=1.0, max_delay=60.0, max_failures=6,
                 max_attempts_per_window=5, window_seconds=60.0,
                 max_keys=128, clock=time.monotonic):
        self._base = _finite_positive(base_delay, "base_delay")
        self._max_delay = _finite_positive(max_delay, "max_delay")
        if self._max_delay < self._base:
            raise LaunchBackoffError("max_delay below base_delay")
        if (type(max_failures) is not int or
                not 1 <= max_failures <= MAX_FAILURES_LIMIT):
            raise LaunchBackoffError("invalid max_failures")
        if (type(max_attempts_per_window) is not int or
                not 1 <= max_attempts_per_window <= MAX_ATTEMPTS_LIMIT):
            raise LaunchBackoffError("invalid max_attempts_per_window")
        if (type(max_keys) is not int or
                not 1 <= max_keys <= MAX_MAX_KEYS):
            raise LaunchBackoffError("invalid max_keys")
        self._window = _finite_positive(window_seconds, "window_seconds")
        if not callable(clock):
            raise LaunchBackoffError("clock must be callable")
        self._max_failures = max_failures
        self._max_attempts = max_attempts_per_window
        self._max_keys = max_keys
        self._clock = clock
        self._states = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def _key(key):
        if type(key) is not str or not KEY.fullmatch(key):
            raise LaunchBackoffError("invalid application key")
        return key

    def _now(self, now):
        if now is None:
            now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise LaunchBackoffError("invalid clock value")
        return float(now)

    def _state(self, key):
        state = self._states.get(key)
        if state is not None:
            self._states.move_to_end(key)
            return state
        if len(self._states) >= self._max_keys:
            self._states.popitem(last=False)
        state = _State(0, None, deque(maxlen=self._max_attempts))
        self._states[key] = state
        return state

    def admit(self, key, now=None):
        """Consume one launch slot when allowed; never mutate on refusal."""
        key = self._key(key)
        now = self._now(now)
        with self._lock:
            state = self._state(key)
            while state.attempts and now - state.attempts[0] >= self._window:
                state.attempts.popleft()
            failures = state.failures
            if failures >= self._max_failures:
                return LaunchDecision(False, SUSPENDED, 0.0, failures)

            backoff = 0.0
            if state.next_allowed is not None and state.next_allowed > now:
                backoff = state.next_allowed - now
            limited = 0.0
            if len(state.attempts) >= self._max_attempts:
                limited = min(self._window, max(0.0,
                             self._window - (now - state.attempts[0])))
            if backoff > 0.0 or limited > 0.0:
                if backoff >= limited:
                    return LaunchDecision(False, BACKOFF, backoff, failures)
                return LaunchDecision(False, RATE_LIMITED, limited, failures)

            state.attempts.append(now)
            return LaunchDecision(True, ADMITTED, 0.0, failures)

    def report_failure(self, key, now=None):
        """Record a crash/failed launch and arm capped exponential backoff."""
        key = self._key(key)
        now = self._now(now)
        with self._lock:
            state = self._state(key)
            state.failures = min(state.failures + 1, self._max_failures)
            if state.failures >= self._max_failures:
                state.next_allowed = None
                return LaunchDecision(False, SUSPENDED, 0.0, state.failures)
            delay = min(self._base * (2 ** (state.failures - 1)), self._max_delay)
            state.next_allowed = now + delay
            return LaunchDecision(False, BACKOFF, delay, state.failures)

    def report_success(self, key):
        """Clear failure streak and backoff; keep the recent-attempt window."""
        key = self._key(key)
        with self._lock:
            state = self._states.get(key)
            if state is not None:
                state.failures = 0
                state.next_allowed = None
                self._states.move_to_end(key)

    def reset(self, key=None):
        """Drop one key, or all tracked state during host recovery."""
        if key is None:
            with self._lock:
                self._states.clear()
            return
        key = self._key(key)
        with self._lock:
            self._states.pop(key, None)

    @property
    def tracked_key_count(self):
        with self._lock:
            return len(self._states)
