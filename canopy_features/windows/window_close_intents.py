"""Offline model of non-destructive window close request semantics.

This mirrors the compiled Classic Files preview contract: QML
``requestClose()`` parks the window (``visible = false``) while FileModel keeps
navigation state, ``closed()`` is emitted on the visibility change, and menu
items can show the same window again. This module models only that decision
and state-preservation logic. It does not load QML, drive Qt, query a
compositor, touch a session, poll, spawn workers or open network sockets.

Windows are registered by trusted host code with an owner token. A close is a
request: it can be refused by the owner's guard, and it never discards state.
Only ``release()`` removes a record, and only for the owning token.
"""

from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType

MAX_WINDOWS = 16
MAX_STATE_FIELDS = 16
MAX_STRING_BYTES = 256
MAX_NUMBER = 1_000_000_000_000

_TOKEN = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_FIELD = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
_VALUE_TYPES = (str, int, float, bool, type(None))

CLOSED = "CLOSED"
ALREADY_CLOSED = "ALREADY_CLOSED"
GUARDED = "GUARDED"
REOPENED = "REOPENED"
ALREADY_OPEN = "ALREADY_OPEN"
UNKNOWN_WINDOW = "UNKNOWN_WINDOW"
OWNERSHIP_DENIED = "OWNERSHIP_DENIED"
STATUSES = frozenset({
    CLOSED, ALREADY_CLOSED, GUARDED, REOPENED, ALREADY_OPEN,
    UNKNOWN_WINDOW, OWNERSHIP_DENIED,
})
ACCEPTED = frozenset({CLOSED, ALREADY_CLOSED, REOPENED, ALREADY_OPEN})

NO_STATE = MappingProxyType({})


class CloseRequestError(ValueError):
    """Invalid registration, state field, guard value or bound."""


@dataclass(frozen=True)
class IntentResult:
    """Decision for one close/reopen request; never an OS or Qt event."""

    window_id: str
    status: str
    visible: bool | None
    state: MappingProxyType = field(default=NO_STATE)
    note: str = ""

    @property
    def accepted(self):
        return self.status in ACCEPTED


@dataclass
class _Window:
    window_id: str
    owner: str
    visible: bool
    guarded: bool
    state: dict
    _state_view: object = None


def _valid_token(value):
    return type(value) is str and bool(_TOKEN.fullmatch(value))


def _safe_id(value):
    return value if type(value) is str else ""


def _encode_state(fields):
    if type(fields) is not dict or len(fields) > MAX_STATE_FIELDS:
        raise CloseRequestError("invalid or oversized window state")
    encoded = {}
    for name, value in fields.items():
        if type(name) is not str or not _FIELD.fullmatch(name):
            raise CloseRequestError("unsupported window state field name")
        if type(value) not in _VALUE_TYPES:
            raise CloseRequestError("nested or untrusted window state value")
        if type(value) is str:
            try:
                size = len(value.encode("utf-8", "strict"))
            except UnicodeError as exc:
                raise CloseRequestError("invalid UTF-8 window state value") from exc
            if size > MAX_STRING_BYTES:
                raise CloseRequestError("window state string exceeds bound")
        elif type(value) is float and (
                not math.isfinite(value) or abs(value) > MAX_NUMBER):
            raise CloseRequestError("non-finite or unbounded window state value")
        elif type(value) is int and abs(value) > MAX_NUMBER:
            raise CloseRequestError("window state integer exceeds bound")
        encoded[name] = value
    return encoded


class CloseIntentModel:
    """Bounded in-memory owner/check/park/reopen state machine.

    Intended for the host event-loop thread. It holds no synchronous state and
    is not thread-safe by design. It is not a window manager or a Qt bridge.
    """

    def __init__(self, max_windows=MAX_WINDOWS):
        if type(max_windows) is not int or not 1 <= max_windows <= MAX_WINDOWS:
            raise CloseRequestError("invalid window limit")
        self._max_windows = max_windows
        self._windows = {}

    @property
    def window_count(self):
        return len(self._windows)

    def _lookup(self, window_id, owner):
        if not _valid_token(window_id) or not _valid_token(owner):
            return None, UNKNOWN_WINDOW
        record = self._windows.get(window_id)
        if record is None:
            return None, UNKNOWN_WINDOW
        if record.owner != owner:
            return None, OWNERSHIP_DENIED
        return record, None

    @staticmethod
    def _result(record, status, note=""):
        return IntentResult(record.window_id, status, record.visible,
                            MappingProxyType(dict(record.state)), note)

    def register(self, window_id, owner, state=None, *, visible=True,
                 guarded=False):
        """Add a host-owned window. Rejects invalid, duplicate or excess IDs."""
        if not _valid_token(window_id):
            raise CloseRequestError("invalid window identifier")
        if not _valid_token(owner):
            raise CloseRequestError("invalid owner token")
        if window_id in self._windows:
            raise CloseRequestError("duplicate window identifier")
        if len(self._windows) >= self._max_windows:
            raise CloseRequestError("window limit reached")
        if type(visible) is not bool or type(guarded) is not bool:
            raise CloseRequestError("visible and guarded must be bool")
        encoded = _encode_state({} if state is None else state)
        self._windows[window_id] = _Window(
            window_id, owner, visible, guarded, encoded)

    def request_close(self, window_id, owner):
        """Park an owned window; a guard or bad caller cannot destroy state."""
        record, denial = self._lookup(window_id, owner)
        if denial is not None:
            return IntentResult(_safe_id(window_id), denial, None, NO_STATE,
                                "close request refused")
        if record.guarded:
            return self._result(record, GUARDED,
                                "owner guard active; window left open")
        if not record.visible:
            return self._result(record, ALREADY_CLOSED,
                                "window already parked; state unchanged")
        record.visible = False
        return self._result(record, CLOSED, "window parked; state preserved")

    def reopen(self, window_id, owner):
        """Show the same stored window; close never discarded its state."""
        record, denial = self._lookup(window_id, owner)
        if denial is not None:
            return IntentResult(_safe_id(window_id), denial, None, NO_STATE,
                                "reopen request refused")
        if record.visible:
            return self._result(record, ALREADY_OPEN,
                                "window already shown; state unchanged")
        record.visible = True
        return self._result(record, REOPENED, "window restored with prior state")

    def set_guard(self, window_id, owner, guarded):
        """Owner-only refusal switch for unsaved-work style close vetoes."""
        record, denial = self._lookup(window_id, owner)
        if denial is not None:
            return False
        if type(guarded) is not bool:
            raise CloseRequestError("guard value must be bool")
        record.guarded = guarded
        return True

    def update_state(self, window_id, owner, **fields):
        """Owner-only bounded state write; returns False on unknown/denied."""
        record, denial = self._lookup(window_id, owner)
        if denial is not None:
            return False
        updates = _encode_state(fields)
        merged = dict(record.state)
        merged.update(updates)
        if len(merged) > MAX_STATE_FIELDS:
            raise CloseRequestError("window state field limit reached")
        record.state = merged
        record._state_view = None
        return True

    def snapshot(self, window_id, owner):
        """Read-only owned state view, or an empty mapping for unknown/denied.

        The immutable view is built lazily and reused until a real state write
        invalidates it; lifecycle changes that leave state untouched do not
        allocate a new view.
        """
        record, denial = self._lookup(window_id, owner)
        if denial is not None:
            return NO_STATE
        if record._state_view is None:
            record._state_view = MappingProxyType(dict(record.state))
        return record._state_view

    def release(self, window_id, owner):
        """Explicitly remove an owned record; this is the destructive path."""
        record, denial = self._lookup(window_id, owner)
        if denial is not None:
            return False
        del self._windows[record.window_id]
        return True
