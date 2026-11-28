"""Bounded M3 window/workspace management plans at the native host boundary.

This module turns one trusted, explicitly supplied desktop snapshot into
decision-only plans for window activation, workspace switching and focus
recovery.  It uses the facilities of the *existing* native session:

* ``org.kde.KWin`` D-Bus (``currentDesktop`` / ``setCurrentDesktop``);
* ``org.freedesktop.DBus`` (capability/name inspection);
* FreeDesktop EWMH root properties (``_NET_ACTIVE_WINDOW``,
  ``_NET_CURRENT_DESKTOP``, ``_NET_DESKTOP_NAMES``, ``_NET_CLIENT_LIST``).

It never opens a socket, grabs the X server, starts a compositor or service,
launches a process, reads the environment, registers a timer or polls.  Each
plan is an immutable command *descriptor* for a trusted reviewed host adapter;
this module never executes it.  No runtime, accessibility or visual result is
claimed here.  A second compositor or duplicated service is never introduced:
there is exactly one authoritative snapshot and one plan fold per call.

Scope boundaries: this is not the legacy workspace-inventory normalizer, the
window activation event boundary, the focus-intent authorizer or a compiled Qt
adapter.  Those modules are reused conceptually and are not modified.
"""
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
import re
import unicodedata

__all__ = [
    "CAPABILITY_METHODS", "DBUS_PATH", "DBUS_SERVICE", "EWMH_PROPERTIES",
    "FACILITIES", "INTENTS", "KWIN_INTERFACE", "KWIN_PATH", "KWIN_SERVICE",
    "MAX_HISTORY", "MAX_NAME_BYTES", "MAX_SOURCE_BYTES", "MAX_WINDOWS",
    "MAX_WORKSPACES", "SCHEMA", "WorkspaceRef", "WindowRef",
    "DesktopSnapshot", "NativeCommand", "RecoveryPlan", "SnapshotError",
    "ManagerClosed", "NativeWindowManager", "parse_snapshot",
]

SCHEMA = 1

KWIN_SERVICE = "org.kde.KWin"
KWIN_PATH = "/KWin"
KWIN_INTERFACE = "org.kde.KWin"
DBUS_SERVICE = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"

EWMH_ACTIVE_WINDOW = "_NET_ACTIVE_WINDOW"
EWMH_CLIENT_LIST = "_NET_CLIENT_LIST"
EWMH_CURRENT_DESKTOP = "_NET_CURRENT_DESKTOP"
EWMH_DESKTOP_NAMES = "_NET_DESKTOP_NAMES"
EWMH_SUPPORTED = "_NET_SUPPORTED"
EWMH_PROPERTIES = frozenset({
    EWMH_ACTIVE_WINDOW, EWMH_CLIENT_LIST, EWMH_CURRENT_DESKTOP,
    EWMH_DESKTOP_NAMES, EWMH_SUPPORTED,
})

FACILITY_KWIN = "kwin-dbus"
FACILITY_DBUS = "freedesktop-dbus"
FACILITY_EWMH = "ewmh-x11"
FACILITIES = frozenset({FACILITY_KWIN, FACILITY_DBUS, FACILITY_EWMH})

CAPABILITY_METHODS = frozenset({"currentDesktop", "setCurrentDesktop"})
INTENTS = frozenset({"inspect", "switch_workspace", "activate", "recover_focus"})

MAX_SOURCE_BYTES = 64
MAX_NAME_BYTES = 128
MAX_ID_BYTES = 64
MAX_WORKSPACES = 64
MAX_WINDOWS = 256
MAX_HISTORY = 16

_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_WINDOW_ID = re.compile(r"0x[0-9a-f]{1,16}\Z")
_SOURCE = re.compile(r"[a-z0-9][a-z0-9_.:+-]{0,63}\Z")
_UNSAFE = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

NO_ACTIVE_WINDOW = ""
NO_COMMAND = "no_command"
NO_FALLBACK = "no_eligible_fallback"


class SnapshotError(ValueError):
    """Malformed, contradictory or out-of-bound trusted host snapshot."""


class ManagerClosed(RuntimeError):
    """Operation attempted after explicit cleanup."""


def _text(value, label, pattern, limit):
    if type(value) is not str or not value:
        raise SnapshotError("invalid " + label)
    if any(unicodedata.category(char) in _UNSAFE for char in value):
        raise SnapshotError("unsafe " + label)
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeEncodeError:
        raise SnapshotError("invalid UTF-8 " + label) from None
    if size > limit or not pattern.fullmatch(value):
        raise SnapshotError("invalid " + label)
    return value


def _name(value, label):
    if type(value) is not str or not value:
        raise SnapshotError("invalid " + label)
    if any(unicodedata.category(char) in _UNSAFE for char in value):
        raise SnapshotError("unsafe " + label)
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeEncodeError:
        raise SnapshotError("invalid UTF-8 " + label) from None
    if not value.strip() or size > MAX_NAME_BYTES:
        raise SnapshotError("invalid " + label)
    return value


def _identifier(value):
    return _text(value, "workspace identifier", _SLUG, MAX_ID_BYTES)


def _window_id(value):
    return _text(value, "window id", _WINDOW_ID, MAX_ID_BYTES)


def _ordinal(value):
    # `bool` is an int subclass; reject it explicitly before any arithmetic.
    if type(value) is not int or not 1 <= value <= MAX_WORKSPACES:
        raise SnapshotError("invalid workspace ordinal")
    return value


def _ordered(value, label):
    # A bare string and bytes are ordered iterables of characters; a set has
    # no order at all.  Neither can define a canonical desktop snapshot.
    if isinstance(value, (str, bytes, bytearray, Mapping)) or not isinstance(value, Sequence):
        raise SnapshotError(label + " must be an ordered sequence")
    return value


@dataclass(frozen=True)
class WorkspaceRef:
    """One KWin virtual desktop in the trusted snapshot."""

    identifier: str
    ordinal: int
    name: str

    def __post_init__(self):
        _identifier(self.identifier)
        _ordinal(self.ordinal)
        _name(self.name, "workspace name")


@dataclass(frozen=True)
class WindowRef:
    """One mapped client window owned by a workspace in the snapshot."""

    window_id: str
    workspace: str
    title: str

    def __post_init__(self):
        _window_id(self.window_id)
        _identifier(self.workspace)
        _name(self.title, "window title")


@dataclass(frozen=True)
class DesktopSnapshot:
    """Immutable, internally consistent view of one desktop at one instant."""

    source: str
    workspaces: tuple
    windows: tuple
    current_workspace: str
    active_window: str

    def __post_init__(self):
        _text(self.source, "source", _SOURCE, MAX_SOURCE_BYTES)
        if not isinstance(self.workspaces, tuple) or not isinstance(self.windows, tuple):
            raise SnapshotError("snapshot collections must be tuples")
        identifiers = [entry.identifier for entry in self.workspaces]
        if len(identifiers) != len(set(identifiers)):
            raise SnapshotError("duplicate workspace identifier")
        ordinals = [entry.ordinal for entry in self.workspaces]
        if len(ordinals) != len(set(ordinals)):
            raise SnapshotError("duplicate workspace ordinal")
        workspace_ids = set(identifiers)
        ids = [entry.window_id for entry in self.windows]
        if len(ids) != len(set(ids)):
            raise SnapshotError("duplicate window id")
        for window in self.windows:
            if not isinstance(window, WindowRef):
                raise SnapshotError("invalid window record")
            if window.workspace not in workspace_ids:
                raise SnapshotError("window references an unknown workspace")
        for workspace in self.workspaces:
            if not isinstance(workspace, WorkspaceRef):
                raise SnapshotError("invalid workspace record")
        _identifier(self.current_workspace)
        if self.current_workspace not in workspace_ids:
            raise SnapshotError("current workspace is not in the inventory")
        if type(self.active_window) is not str:
            raise SnapshotError("active window must be a string")
        if self.active_window:
            _window_id(self.active_window)
            if self.active_window not in set(ids):
                raise SnapshotError("active window is not in the snapshot")
            active = next(w for w in self.windows if w.window_id == self.active_window)
            if active.workspace != self.current_workspace:
                raise SnapshotError("active window is not on the current workspace")

    def workspace(self, identifier):
        """Bounded exact lookup; fail closed on a wrong-type argument."""
        if type(identifier) is not str:
            raise SnapshotError("workspace lookup requires a string")
        for entry in self.workspaces:
            if entry.identifier == identifier:
                return entry
        return None

    def window(self, window_id):
        """Bounded exact lookup; fail closed on a wrong-type argument."""
        if type(window_id) is not str:
            raise SnapshotError("window lookup requires a string")
        for entry in self.windows:
            if entry.window_id == window_id:
                return entry
        return None


def parse_snapshot(record):
    """Normalize one trusted host mapping into a `DesktopSnapshot`.

    The caller supplies a single explicit snapshot.  Every field is type-,
    bound- and consistency-checked before use; no host resource is touched.
    """
    if not isinstance(record, Mapping):
        raise SnapshotError("snapshot must be a mapping")
    source = _text(record.get("source"), "source", _SOURCE, MAX_SOURCE_BYTES)
    raw_workspaces = _ordered(record.get("workspaces", ()), "workspaces")
    raw_windows = _ordered(record.get("windows", ()), "windows")
    if len(raw_workspaces) > MAX_WORKSPACES or len(raw_windows) > MAX_WINDOWS:
        raise SnapshotError("snapshot exceeds inventory bound")
    workspaces = []
    for raw in raw_workspaces:
        if not isinstance(raw, Mapping):
            raise SnapshotError("workspace record must be a mapping")
        workspaces.append(WorkspaceRef(
            identifier=_identifier(raw.get("identifier")),
            ordinal=_ordinal(raw.get("ordinal")),
            name=_name(raw.get("name"), "workspace name"),
        ))
    windows = []
    for raw in raw_windows:
        if not isinstance(raw, Mapping):
            raise SnapshotError("window record must be a mapping")
        windows.append(WindowRef(
            window_id=_window_id(raw.get("window_id")),
            workspace=_identifier(raw.get("workspace")),
            title=_name(raw.get("title"), "window title"),
        ))
    return DesktopSnapshot(
        source=source,
        workspaces=tuple(workspaces),
        windows=tuple(windows),
        current_workspace=_identifier(record.get("current_workspace")),
        active_window=(_window_id(record["active_window"])
                       if record.get("active_window") else NO_ACTIVE_WINDOW),
    )


@dataclass(frozen=True)
class NativeCommand:
    """One reviewed-facility command descriptor.  Never self-executing."""

    intent: str
    facility: str
    operation: str
    arguments: tuple
    verify_property: str

    def __post_init__(self):
        if type(self.intent) is not str or self.intent not in INTENTS:
            raise SnapshotError("invalid command intent")
        if type(self.facility) is not str or self.facility not in FACILITIES:
            raise SnapshotError("unapproved command facility")
        if type(self.operation) is not str or not self.operation:
            raise SnapshotError("invalid command operation")
        if type(self.arguments) is not tuple:
            raise SnapshotError("command arguments must be a tuple")
        if type(self.verify_property) is not str or not self.verify_property:
            raise SnapshotError("invalid verification property")
        if self.facility == FACILITY_KWIN:
            if self.operation not in CAPABILITY_METHODS:
                raise SnapshotError("KWin operation is not allowlisted")
            if self.verify_property != "currentDesktop":
                raise SnapshotError("KWin command must be read back via currentDesktop")
        if self.facility == FACILITY_EWMH:
            if self.operation not in EWMH_PROPERTIES:
                raise SnapshotError("EWMH property is not allowlisted")
            if self.verify_property != EWMH_ACTIVE_WINDOW:
                raise SnapshotError("activation must be read back via _NET_ACTIVE_WINDOW")

    def to_dict(self):
        """Fresh read-only projection in fixed order."""
        return MappingProxyType({
            "intent": self.intent,
            "facility": self.facility,
            "operation": self.operation,
            "arguments": self.arguments,
            "verify_property": self.verify_property,
            "executed": False,
        })


@dataclass(frozen=True)
class RecoveryPlan:
    """Decision with at most one command and explicit non-claims."""

    outcome: str
    reason: str
    command: object
    schema: int = SCHEMA
    observation: str = "NOT_PERFORMED"
    runtime: str = "NOT_RUN"
    screen_reader: str = "NOT_RUN"
    duplicate_compositors: int = 0

    def __post_init__(self):
        if type(self.outcome) is not str or self.outcome not in (
                "planned", NO_COMMAND, "no_facts"):
            raise SnapshotError("invalid plan outcome")
        if type(self.reason) is not str or not self.reason:
            raise SnapshotError("invalid plan reason")
        if self.command is not None and not isinstance(self.command, NativeCommand):
            raise SnapshotError("plan command must be a NativeCommand or None")
        if (self.outcome == "planned") != (self.command is not None):
            raise SnapshotError("plan outcome and command disagree")
        if self.schema != SCHEMA:
            raise SnapshotError("invalid plan schema")
        for label, expected in (("observation", "NOT_PERFORMED"),
                                ("runtime", "NOT_RUN"),
                                ("screen_reader", "NOT_RUN")):
            value = getattr(self, label)
            if type(value) is not str or value != expected:
                raise SnapshotError("invalid " + label + " claim")
        if type(self.duplicate_compositors) is not int or self.duplicate_compositors:
            raise SnapshotError("duplicate compositor claim must be zero")

    def to_dict(self):
        return MappingProxyType({
            "schema": self.schema,
            "outcome": self.outcome,
            "reason": self.reason,
            "command": self.command.to_dict() if self.command is not None else None,
            "observation": self.observation,
            "runtime": self.runtime,
            "screen_reader": self.screen_reader,
            "duplicate_compositors": self.duplicate_compositors,
        })


class NativeWindowManager:
    """Single-threaded, bounded fold over one authoritative snapshot."""

    def __init__(self, snapshot=None, *, history_limit=MAX_HISTORY):
        if snapshot is not None and not isinstance(snapshot, DesktopSnapshot):
            raise SnapshotError("snapshot must be a DesktopSnapshot")
        if type(history_limit) is not int or not 1 <= history_limit <= MAX_HISTORY:
            raise SnapshotError("invalid history bound")
        self._snapshot = snapshot
        self._history = deque(maxlen=history_limit)
        self._history_cache = None
        self._rejections = 0
        self._closed = False

    def _ready(self):
        if self._closed:
            raise ManagerClosed("native window manager is closed")

    def ingest(self, snapshot):
        """Replace the one authoritative snapshot with another trusted view."""
        self._ready()
        if not isinstance(snapshot, DesktopSnapshot):
            self._rejections += 1
            raise SnapshotError("snapshot must be a DesktopSnapshot")
        self._snapshot = snapshot
        self._history_cache = None
        return snapshot.source

    @property
    def snapshot(self):
        return self._snapshot

    @property
    def history(self):
        if self._history_cache is None:
            self._history_cache = tuple(self._history)
        return self._history_cache

    @property
    def rejections(self):
        return self._rejections

    @property
    def closed(self):
        return self._closed

    def _require_snapshot(self):
        self._ready()
        if self._snapshot is None:
            self._rejections += 1
            raise SnapshotError("no authoritative snapshot has been supplied")
        return self._snapshot

    def workspace_inventory(self):
        """Read-only inventory from the authoritative snapshot."""
        snapshot = self._require_snapshot()
        return tuple((entry.identifier, entry.ordinal, entry.name)
                     for entry in snapshot.workspaces)

    def plan_workspace_switch(self, identifier):
        """Plan a KWin D-Bus desktop switch with currentDesktop read-back."""
        snapshot = self._require_snapshot()
        workspace = snapshot.workspace(identifier)
        if workspace is None:
            return RecoveryPlan(NO_COMMAND, "unknown_workspace", None)
        if workspace.identifier == snapshot.current_workspace:
            return RecoveryPlan(NO_COMMAND, "already_on_workspace", None)
        command = NativeCommand(
            intent="switch_workspace", facility=FACILITY_KWIN,
            operation="setCurrentDesktop", arguments=(workspace.ordinal,),
            verify_property="currentDesktop",
        )
        self._history.append(command)
        self._history_cache = None
        return RecoveryPlan("planned", "capability_granted", command)

    def plan_activation(self, window_id):
        """Plan an EWMH activation with _NET_ACTIVE_WINDOW read-back."""
        snapshot = self._require_snapshot()
        if type(window_id) is not str:
            self._rejections += 1
            raise SnapshotError("activation requires a string window id")
        window = snapshot.window(window_id)
        if window is None:
            return RecoveryPlan(NO_COMMAND, "unknown_window", None)
        if window.workspace != snapshot.current_workspace:
            return RecoveryPlan(NO_COMMAND, "off_workspace_window", None)
        command = NativeCommand(
            intent="activate", facility=FACILITY_EWMH,
            operation=EWMH_ACTIVE_WINDOW, arguments=(window.window_id,),
            verify_property=EWMH_ACTIVE_WINDOW,
        )
        self._history.append(command)
        self._history_cache = None
        return RecoveryPlan("planned", "window_visible", command)

    def plan_focus_recovery(self, lost_window_id):
        """Plan focus recovery to the most recent other window on this desktop.

        Recovery never resurrects the lost window and never crosses a
        workspace boundary.  The fallback is drawn only from the one
        authoritative snapshot; if none is eligible the plan is explicitly
        empty rather than guessed.
        """
        snapshot = self._require_snapshot()
        if type(lost_window_id) is not str:
            self._rejections += 1
            raise SnapshotError("recovery requires a string window id")
        candidates = [window for window in snapshot.windows
                      if window.workspace == snapshot.current_workspace
                      and window.window_id != lost_window_id]
        if not candidates:
            return RecoveryPlan(NO_COMMAND, NO_FALLBACK, None)
        fallback = candidates[-1]
        command = NativeCommand(
            intent="recover_focus", facility=FACILITY_EWMH,
            operation=EWMH_ACTIVE_WINDOW, arguments=(fallback.window_id,),
            verify_property=EWMH_ACTIVE_WINDOW,
        )
        self._history.append(command)
        self._history_cache = None
        return RecoveryPlan("planned", "fallback_from_snapshot", command)

    def observe(self, *, current_workspace=None, active_window=None):
        """Fold one trusted read-back result into the authoritative state.

        Untrusted callers cannot mutate state: a value must be a member of the
        current snapshot, and a contradictory pair is refused.  No observation
        is claimed by this method itself; the transport remains the caller's.
        """
        snapshot = self._require_snapshot()
        next_workspace = snapshot.current_workspace
        next_active = snapshot.active_window
        if current_workspace is not None:
            if type(current_workspace) is not str:
                self._rejections += 1
                raise SnapshotError("read-back workspace must be a string")
            if snapshot.workspace(current_workspace) is None:
                self._rejections += 1
                raise SnapshotError("read-back workspace is not in the snapshot")
            next_workspace = current_workspace
        if active_window is not None:
            if type(active_window) is not str:
                self._rejections += 1
                raise SnapshotError("read-back window must be a string")
            window = snapshot.window(active_window)
            if window is None:
                self._rejections += 1
                raise SnapshotError("read-back window is not in the snapshot")
            if window.workspace != next_workspace:
                self._rejections += 1
                raise SnapshotError("read-back window is off the current workspace")
            next_active = active_window
        updated = DesktopSnapshot(
            source=snapshot.source, workspaces=snapshot.workspaces,
            windows=snapshot.windows, current_workspace=next_workspace,
            active_window=next_active,
        )
        self._snapshot = updated
        return updated

    def snapshot_state(self):
        """Read-only shell view with fixed negative claims and no callback."""
        snapshot = self._require_snapshot()
        return MappingProxyType({
            "schema": SCHEMA,
            "source": snapshot.source,
            "current_workspace": snapshot.current_workspace,
            "active_window": snapshot.active_window,
            "workspace_count": len(snapshot.workspaces),
            "window_count": len(snapshot.windows),
            "history_count": len(self._history),
            "rejections": self._rejections,
            "observation": "NOT_PERFORMED",
            "runtime": "NOT_RUN",
            "screen_reader": "NOT_RUN",
            "duplicate_compositors": 0,
        })

    def close(self):
        """Drop the snapshot and plan history; no further operation is valid."""
        if self._closed:
            return
        self._snapshot = None
        self._history.clear()
        self._history_cache = None
        self._closed = True
