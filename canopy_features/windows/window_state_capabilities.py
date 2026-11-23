"""Minimize/maximize window-state capabilities with backend feature negotiation.

Offline, in-process policy component. It does NOT talk to Qt, X11, Wayland,
Cinnamon, the Windows API or any compositor. A trusted caller supplies an
advertised backend profile; this module only negotiates the overlapping feature
set and enforces a small, bounded state machine.

Limits, by design:
- No polling, threads, background services, I/O, privileged calls or caches.
- Known backend profiles are policy examples reflecting core protocol
  expectations, not measured behaviour of any compositor or session.
- An unrecognised backend advertises no features (fail closed).
- RESTORE always returns to NORMAL. Minimizing an already maximized window is
  refused rather than guessing a prior state, keeping state bounded.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Collection, FrozenSet

__all__ = [
    "WindowStateAction",
    "WindowStateFeature",
    "WindowState",
    "BackendProfile",
    "Negotiation",
    "TransitionResult",
    "WindowStateController",
    "profile_for",
    "negotiate",
    "KNOWN_BACKENDS",
    "ACTION_FEATURE",
    "VALID_TRANSITIONS",
]


class WindowStateAction(Enum):
    """Actions a caller may request for one window."""

    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    RESTORE = "restore"


class WindowStateFeature(Enum):
    """Features a backend may advertise."""

    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    RESTORE = "restore"


class WindowState(Enum):
    """The single, current state of one managed window."""

    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"


ACTION_FEATURE = MappingProxyType({
    WindowStateAction.MINIMIZE: WindowStateFeature.MINIMIZE,
    WindowStateAction.MAXIMIZE: WindowStateFeature.MAXIMIZE,
    WindowStateAction.RESTORE: WindowStateFeature.RESTORE,
})

VALID_TRANSITIONS = MappingProxyType({
    (WindowState.NORMAL, WindowStateAction.MINIMIZE): WindowState.MINIMIZED,
    (WindowState.NORMAL, WindowStateAction.MAXIMIZE): WindowState.MAXIMIZED,
    (WindowState.MINIMIZED, WindowStateAction.RESTORE): WindowState.NORMAL,
    (WindowState.MAXIMIZED, WindowStateAction.RESTORE): WindowState.NORMAL,
})


@dataclass(frozen=True)
class BackendProfile:
    """Immutable capability advertisement from a trusted caller."""

    name: str
    supported: FrozenSet[WindowStateFeature]

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("backend name must be a non-empty string")
        if not isinstance(self.supported, frozenset):
            raise TypeError("supported must be a frozenset")
        for feature in self.supported:
            if not isinstance(feature, WindowStateFeature):
                raise TypeError("advertised features must be WindowStateFeature values")

    def supports(self, feature: WindowStateFeature) -> bool:
        return feature in self.supported


def _profile(name, *features):
    return BackendProfile(name, frozenset(features))


_X11 = _profile(
    "x11",
    WindowStateFeature.MINIMIZE,
    WindowStateFeature.MAXIMIZE,
    WindowStateFeature.RESTORE,
)
# Core Wayland has no minimize request; a compositor extension would be needed.
_WAYLAND = _profile(
    "wayland",
    WindowStateFeature.MAXIMIZE,
    WindowStateFeature.RESTORE,
)
_HEADLESS = _profile("headless")

KNOWN_BACKENDS = MappingProxyType({
    profile.name: profile for profile in (_X11, _WAYLAND, _HEADLESS)
})


def profile_for(name: str) -> BackendProfile:
    """Return a known profile, or an empty fail-closed profile for unknown ids.

    Unknown names are never inserted into KNOWN_BACKENDS, so lookups cannot
    grow memory or let an arbitrary id acquire capabilities.
    """
    if not isinstance(name, str):
        raise TypeError("backend name must be a string")
    profile = KNOWN_BACKENDS.get(name)
    if profile is not None:
        return profile
    return BackendProfile(name, frozenset())


@dataclass(frozen=True)
class Negotiation:
    """The agreed feature set for one backend and one requested set."""

    backend: str
    status: str  # SUPPORTED, PARTIAL or UNSUPPORTED
    granted: FrozenSet[WindowStateFeature]

    @property
    def supported(self) -> bool:
        return bool(self.granted)

    def allows(self, action: WindowStateAction) -> bool:
        try:
            feature = ACTION_FEATURE.get(action)
        except TypeError:
            return False
        return feature is not None and feature in self.granted


def negotiate(backend, requested: Collection[WindowStateFeature]) -> Negotiation:
    """Intersect a backend's advertised features with the requested features."""
    if isinstance(backend, BackendProfile):
        profile = backend
    elif isinstance(backend, str):
        profile = profile_for(backend)
    else:
        raise TypeError("backend must be a name or a BackendProfile")
    if isinstance(requested, (str, bytes)):
        raise TypeError("requested must be a collection of WindowStateFeature values")
    try:
        requested_set = frozenset(requested)
    except TypeError:
        raise TypeError("requested must be iterable") from None
    if not requested_set:
        raise ValueError("requested must not be empty")
    for feature in requested_set:
        if not isinstance(feature, WindowStateFeature):
            raise TypeError("requested contains a non-WindowStateFeature value")

    granted = requested_set & profile.supported
    if not granted:
        status = "UNSUPPORTED"
    elif granted == requested_set:
        status = "SUPPORTED"
    else:
        status = "PARTIAL"
    return Negotiation(profile.name, status, granted)


@dataclass(frozen=True)
class TransitionResult:
    """Outcome of one requested state change. State is unchanged on REJECTED."""

    status: str  # OK or REJECTED
    state: WindowState
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "OK"


class WindowStateController:
    """One-window state machine gated by a negotiated feature set.

    Slots and a single state field keep memory bounded: no history, timers or
    background work. Callers own any window handle; this class never touches it.
    """

    __slots__ = ("_negotiation", "_state")

    def __init__(self, negotiation: Negotiation):
        if not isinstance(negotiation, Negotiation):
            raise TypeError("negotiation must be a Negotiation")
        self._negotiation = negotiation
        self._state = WindowState.NORMAL

    @property
    def state(self) -> WindowState:
        return self._state

    @property
    def negotiation(self) -> Negotiation:
        return self._negotiation

    def allows(self, action: WindowStateAction) -> bool:
        return self._negotiation.allows(action)

    def apply(self, action: WindowStateAction) -> TransitionResult:
        try:
            feature = ACTION_FEATURE.get(action)
        except TypeError:
            feature = None
        if feature is None:
            return TransitionResult("REJECTED", self._state, "UNKNOWN_ACTION")

        if feature not in self._negotiation.granted:
            return TransitionResult("REJECTED", self._state, "FEATURE_NOT_GRANTED")

        next_state = VALID_TRANSITIONS.get((self._state, action))
        if next_state is None:
            return TransitionResult("REJECTED", self._state, "INVALID_TRANSITION")
        self._state = next_state
        return TransitionResult("OK", next_state)
