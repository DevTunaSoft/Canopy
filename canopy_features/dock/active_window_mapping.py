"""Offline mapper from focused window IDs to trusted Classic dock tiles.

Small, in-process, event-driven state machine. It observes nothing: a future
reviewed Qt/compositor adapter must feed it explicit focus events. It adds no
polling, timer, thread, socket, process, filesystem or privileged call, and
its state is O(1), so it cannot grow without bound.

Trust model: only names in TRUSTED_TILES (the settled Classic dock set) can
ever be returned. Owner-to-tile resolution uses an explicit allowlist built
by trusted host code; window event data can never add an entry. An owner
outside that allowlist maps to no tile (fail closed). Focus events carry a
host/compositor sequence number, so a late or out-of-order event cannot
override a newer focus; ties are last-writer-wins.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

# Exact settled Classic dock labels. Nothing from a window event can create
# a tile outside this set. Mirrors the approved icon manifest and Main.qml.
TRUSTED_TILES = frozenset({
    "Browser", "Mail", "Files", "Calendar",
    "Photos", "Music", "Terminal", "Settings",
})

# Trusted owner -> tile allowlist. Tokens mirror the exact desktop IDs in
# SystemAppLauncher.cpp so a focused window resolves to the same tile its
# launcher would open. Ambiguous IDs (e.g. org.gnome.Evolution.desktop,
# listed for both Mail and Calendar) are intentionally absent: ambiguity
# fails closed instead of guessing a tile. A future host adapter supplies
# its own curated allowlist, still restricted to TRUSTED_TILES.
DEFAULT_OWNER_TILES = MappingProxyType({
    "firefox.desktop": "Browser",
    "org.mozilla.firefox.desktop": "Browser",
    "chromium.desktop": "Browser",
    "google-chrome.desktop": "Browser",
    "org.gnome.Epiphany.desktop": "Browser",
    "thunderbird.desktop": "Mail",
    "org.mozilla.Thunderbird.desktop": "Mail",
    "nemo.desktop": "Files",
    "org.gnome.Nautilus.desktop": "Files",
    "thunar.desktop": "Files",
    "org.gnome.Calendar.desktop": "Calendar",
    "pix.desktop": "Photos",
    "org.gnome.Loupe.desktop": "Photos",
    "gthumb.desktop": "Photos",
    "rhythmbox.desktop": "Music",
    "org.gnome.Rhythmbox3.desktop": "Music",
    "org.gnome.Lollypop.desktop": "Music",
    "gnome-terminal.desktop": "Terminal",
    "org.gnome.Terminal.desktop": "Terminal",
    "mate-terminal.desktop": "Terminal",
    "xfce4-terminal.desktop": "Terminal",
    "cinnamon-settings.desktop": "Settings",
    "org.gnome.Settings.desktop": "Settings",
    "xfce4-settings-manager.desktop": "Settings",
})

# Bounds keep inputs finite and memory constant; no dynamic growth exists.
MAX_OWNER_ENTRIES = 256
MAX_OWNER_CHARS = 128
MAX_WINDOW_ID = 1_000_000_000_000
MAX_SEQUENCE = 1_000_000_000_000

STATE_FOCUSED = "focused"
STATE_CLOSED = "closed"

MAPPED = "MAPPED"
UNKNOWN_OWNER = "UNKNOWN_OWNER"
STALE_EVENT = "STALE_EVENT"
IGNORED = "IGNORED"
WINDOW_CLOSED = "WINDOW_CLOSED"


class MappingError(ValueError):
    """Invalid allowlist, event or bridge payload at a trust boundary."""


def _valid_window_id(window_id):
    return type(window_id) is int and 1 <= window_id <= MAX_WINDOW_ID


def _valid_sequence(sequence):
    return type(sequence) is int and 0 <= sequence <= MAX_SEQUENCE


def _valid_owner(owner):
    return type(owner) is str and 0 < len(owner) <= MAX_OWNER_CHARS


def _vetted_allowlist(owner_tiles):
    if not isinstance(owner_tiles, Mapping):
        raise MappingError("explicit owner-to-tile allowlist required")
    if len(owner_tiles) > MAX_OWNER_ENTRIES:
        raise MappingError("allowlist exceeds bounded entry count")
    vetted = {}
    for owner, tile in owner_tiles.items():
        if not _valid_owner(owner):
            raise MappingError("invalid owner token in allowlist")
        if type(tile) is not str or tile not in TRUSTED_TILES:
            raise MappingError("allowlist may only target trusted dock tiles")
        vetted[owner] = tile
    return MappingProxyType(vetted)


@dataclass(frozen=True)
class FocusEvent:
    """One focus transition from a trusted window source."""

    window_id: int
    owner: str
    sequence: int

    def __post_init__(self):
        if not _valid_window_id(self.window_id):
            raise MappingError("invalid window ID")
        if not _valid_owner(self.owner):
            raise MappingError("invalid owner token")
        if not _valid_sequence(self.sequence):
            raise MappingError("invalid focus sequence")


@dataclass(frozen=True)
class FocusState:
    """Bounded snapshot a presentation adapter can render."""

    window_id: Optional[int] = None
    tile: Optional[str] = None
    sequence: int = -1


@dataclass(frozen=True)
class MappingResult:
    """Outcome of one event: what is focused now and why."""

    status: str
    window_id: Optional[int]
    tile: Optional[str]
    sequence: int

    @property
    def active(self):
        return self.tile is not None


class ActiveWindowMapping:
    """Map focused window IDs to trusted dock tiles, handling focus races.

    State is a single FocusState. Events strictly older than the last applied
    sequence are dropped; an equal sequence is applied (last writer wins).
    No registration table is kept, so memory stays constant.
    """

    def __init__(self, owner_tiles=DEFAULT_OWNER_TILES):
        self._owner_tiles = _vetted_allowlist(owner_tiles)
        self._focus = FocusState()

    @property
    def state(self):
        return self._focus

    @property
    def owner_tiles(self):
        return self._owner_tiles

    def _current(self, status):
        return MappingResult(status, self._focus.window_id,
                             self._focus.tile, self._focus.sequence)

    def on_focus(self, event):
        """Apply a FocusEvent; ignore stale focus, fail closed on owner."""
        if type(event) is not FocusEvent:
            raise MappingError("FocusEvent required")
        if event.sequence < self._focus.sequence:
            return self._current(STALE_EVENT)
        tile = self._owner_tiles.get(event.owner)
        self._focus = FocusState(event.window_id, tile, event.sequence)
        return MappingResult(MAPPED if tile is not None else UNKNOWN_OWNER,
                             event.window_id, tile, event.sequence)

    def window_closed(self, window_id, sequence):
        """Clear focus only for a matching window and a non-stale sequence."""
        if not _valid_window_id(window_id):
            raise MappingError("invalid window ID")
        if not _valid_sequence(sequence):
            raise MappingError("invalid focus sequence")
        if sequence < self._focus.sequence:
            return self._current(STALE_EVENT)
        if window_id != self._focus.window_id:
            return self._current(IGNORED)
        self._focus = FocusState(None, None, sequence)
        return MappingResult(WINDOW_CLOSED, None, None, sequence)

    def clear(self):
        """Host lifecycle cleanup: drop focus state, keep the allowlist."""
        self._focus = FocusState(None, None, self._focus.sequence)

    def on_window_event(self, event):
        """Consume a canopy_core.host_events window.state.changed event.

        Accepted fields: window_id (int), sequence (int), optional state
        ("focused" default or "closed") and owner (str, focused only).
        Unknown states are ignored without changing focus.
        """
        payload = event.payload
        state = payload.get("state", STATE_FOCUSED)
        if state == STATE_CLOSED:
            return self.window_closed(payload["window_id"],
                                      payload["sequence"])
        if state != STATE_FOCUSED:
            return self._current(IGNORED)
        return self.on_focus(FocusEvent(payload["window_id"],
                                        payload["owner"],
                                        payload["sequence"]))
