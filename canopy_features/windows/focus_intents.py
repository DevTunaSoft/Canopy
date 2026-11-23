"""Offline model of window focus requests with explicit backend authorization.

Scope and limits:
- Pure in-memory logic. No Qt, compositor, X11/Wayland, D-Bus, sockets, threads,
  timers or polling. Trusted host code supplies the ``authorize`` and optional
  ``activate`` callbacks; this module performs no privileged action itself.
- Every request is denied unless the backend returns the exact boolean ``True``.
- A window identity carries a process-local monotonic serial. Reusing a window
  id after destruction yields a new serial, so an old intent can never match
  the new window (stale-target protection without unbounded id history).
- State is bounded. This is not a running desktop, a permission sandbox, or
  proof of Linux Mint, Qt or compositor integration.
"""
from collections import deque
from dataclasses import dataclass
import re
from typing import Iterable, Optional, Tuple

PROTOCOL_VERSION = 1
MAX_LIVE_WINDOWS = 256
MAX_HISTORY = 64
MAX_GRANTS = 256
MAX_WINDOW_ID = 2_147_483_647

APP_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")

GRANTED = "GRANTED"
DENIED = "DENIED"
STALE_TARGET = "STALE_TARGET"
UNKNOWN_TARGET = "UNKNOWN_TARGET"
ACTIVATION_FAILED = "ACTIVATION_FAILED"


class FocusIntentError(ValueError):
    """Invalid input or a violated explicit bound; never a policy outcome."""


def _valid_app_id(app_id, label):
    if type(app_id) is not str or not APP_ID.fullmatch(app_id):
        raise FocusIntentError("invalid " + label)
    return app_id


def _valid_window_id(window_id):
    if type(window_id) is not int or not 1 <= window_id <= MAX_WINDOW_ID:
        raise FocusIntentError("invalid window id")
    return window_id


@dataclass(frozen=True)
class WindowRef:
    """Opaque, single-use reference to one registered window instance."""

    window_id: int
    serial: int

    def __post_init__(self):
        _valid_window_id(self.window_id)
        if type(self.serial) is not int or self.serial < 1:
            raise FocusIntentError("invalid window serial")


@dataclass(frozen=True)
class FocusIntent:
    """A request by ``origin_app`` to focus the window named by ``target``."""

    origin_app: str
    target: WindowRef

    def __post_init__(self):
        _valid_app_id(self.origin_app, "origin app id")
        if type(self.target) is not WindowRef:
            raise FocusIntentError("intent target must be a WindowRef")


@dataclass(frozen=True)
class FocusDecision:
    """Immutable outcome of one focus request."""

    status: str
    intent: FocusIntent
    target_app: Optional[str] = None
    reason: str = ""

    @property
    def allowed(self):
        return self.status == GRANTED


class PermissionPolicy:
    """Deny-by-default, bounded cross-app focus policy for host code.

    ``authorize`` is the explicit backend check consumed by :class:`FocusBroker`.
    Focus within one app is allowed; across apps it needs a recorded grant.
    """

    def __init__(self, grants: Iterable[Tuple[str, str]] = ()):
        self._grants = set()
        for pair in grants:
            self._add(pair)

    def _add(self, pair):
        if type(pair) not in (tuple, list) or len(pair) != 2:
            raise FocusIntentError("grant must be an (origin, target) pair")
        origin, target = pair
        _valid_app_id(origin, "grant origin app id")
        _valid_app_id(target, "grant target app id")
        if len(self._grants) >= MAX_GRANTS:
            raise FocusIntentError("grant limit reached")
        self._grants.add((origin, target))

    def grant(self, origin_app, target_app):
        self._add((origin_app, target_app))

    def revoke(self, origin_app, target_app):
        _valid_app_id(origin_app, "origin app id")
        _valid_app_id(target_app, "target app id")
        self._grants.discard((origin_app, target_app))

    def authorize(self, origin_app, target_app):
        _valid_app_id(origin_app, "origin app id")
        _valid_app_id(target_app, "target app id")
        if origin_app == target_app:
            return True
        return (origin_app, target_app) in self._grants

    @property
    def grant_count(self):
        return len(self._grants)


class FocusBroker:
    """Resolve focus intents against live windows and an explicit backend.

    The backend callable is required and consulted on every fresh target.
    Unknown and stale targets fail closed before the backend is called.
    """

    def __init__(self, authorize, activate=None, *,
                 max_live_windows=MAX_LIVE_WINDOWS):
        if not callable(authorize):
            raise FocusIntentError("explicit authorize backend required")
        if activate is not None and not callable(activate):
            raise FocusIntentError("activate must be callable or None")
        if (type(max_live_windows) is not int
                or not 1 <= max_live_windows <= MAX_LIVE_WINDOWS):
            raise FocusIntentError("invalid live window bound")
        self._authorize = authorize
        self._activate = activate
        self._max_live = max_live_windows
        self._live = {}  # window_id -> (owner app_id, serial)
        self._next_serial = 1
        self._history = deque(maxlen=MAX_HISTORY)

    def register_window(self, app_id, window_id):
        _valid_app_id(app_id, "window owner app id")
        _valid_window_id(window_id)
        if window_id in self._live:
            raise FocusIntentError("window id already registered")
        if len(self._live) >= self._max_live:
            raise FocusIntentError("live window limit reached")
        serial = self._next_serial
        self._next_serial += 1
        self._live[window_id] = (app_id, serial)
        return WindowRef(window_id, serial)

    def unregister_window(self, window_id):
        _valid_window_id(window_id)
        return self._live.pop(window_id, None) is not None

    @property
    def live_window_count(self):
        return len(self._live)

    @property
    def history(self):
        return tuple(self._history)

    def _record(self, decision):
        self._history.append(decision)
        return decision

    def request_focus(self, intent):
        if type(intent) is not FocusIntent:
            raise FocusIntentError("intent must be a FocusIntent")
        ref = intent.target
        entry = self._live.get(ref.window_id)
        if entry is None:
            return self._record(FocusDecision(UNKNOWN_TARGET, intent))
        target_app, serial = entry
        if serial != ref.serial:
            return self._record(FocusDecision(STALE_TARGET, intent, target_app))

        # Explicit backend authorization: only the exact boolean True grants.
        try:
            approved = self._authorize(intent.origin_app, target_app)
        except Exception as exc:
            return self._record(FocusDecision(
                DENIED, intent, target_app, "backend error: " + type(exc).__name__))
        if approved is not True:
            return self._record(FocusDecision(DENIED, intent, target_app))

        if self._activate is not None:
            try:
                activated = self._activate(ref.window_id)
            except Exception as exc:
                return self._record(FocusDecision(
                    ACTIVATION_FAILED, intent, target_app,
                    "activation error: " + type(exc).__name__))
            if activated is False:
                return self._record(FocusDecision(
                    ACTIVATION_FAILED, intent, target_app, "activation refused"))
        return self._record(FocusDecision(GRANTED, intent, target_app))
