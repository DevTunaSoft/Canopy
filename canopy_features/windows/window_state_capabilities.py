"""Minimize/maximize window-state capabilities with backend feature negotiation.

Offline, in-process policy component. It does NOT talk to Qt, X11, Wayland,
Cinnamon, the Windows API or any compositor. A trusted caller supplies an
advertised backend profile; this module only negotiates the overlapping feature
set and enforces a small, bounded state machine. Callers may bind a controller
to a bounded ``WindowStateRegistry`` so each decision carries a fresh,
authorized ``WindowStateRef``; stale, unknown and forged references are refused
before any state change, with no observation of a real window handle.

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
import re
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
    "WindowStateRef",
    "WindowStateRegistry",
    "WindowReferenceError",
    "profile_for",
    "negotiate",
    "KNOWN_BACKENDS",
    "ACTION_FEATURE",
    "VALID_TRANSITIONS",
    "MAX_WINDOW_ID",
    "MAX_SERIAL",
    "MAX_LIVE_WINDOWS",
    "REF_LIVE",
    "REF_STALE",
    "REF_UNKNOWN",
    "REF_UNAUTHORIZED",
    "INVALID_REFERENCE",
    "UNKNOWN_REFERENCE",
    "STALE_REFERENCE",
    "UNAUTHORIZED_REFERENCE",
    "UNVALIDATED_REFERENCE",
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


_NEGOTIATION_STATUSES = frozenset({"SUPPORTED", "PARTIAL", "UNSUPPORTED"})


def _valid_grants(granted):
    """Return the grant set only if its container and values are trusted."""
    if not isinstance(granted, frozenset):
        return frozenset()
    for feature in granted:
        if not isinstance(feature, WindowStateFeature):
            return frozenset()
    return granted


def _effective_grants(negotiation):
    """Grants usable for a decision: well-typed and consistent with the record."""
    if (not isinstance(negotiation.backend, str)
            or not negotiation.backend
            or not isinstance(negotiation.status, str)
            or negotiation.status not in _NEGOTIATION_STATUSES):
        return frozenset()
    granted = _valid_grants(negotiation.granted)
    # SUPPORTED/PARTIAL promise at least one grant; UNSUPPORTED promises none.
    if (negotiation.status == "UNSUPPORTED") != (not granted):
        return frozenset()
    # A known backend name binds the record to that profile's advertisement.
    # Grants outside it (for example minimize on Wayland or any grant on
    # headless) would be a false capability claim at every decision point.
    try:
        profile = KNOWN_BACKENDS.get(negotiation.backend)
    except (TypeError, ValueError):
        return frozenset()
    if profile is not None and not granted <= profile.supported:
        return frozenset()
    return granted


@dataclass(frozen=True)
class Negotiation:
    """The agreed feature set for one backend and one requested set."""

    backend: str
    status: str  # SUPPORTED, PARTIAL or UNSUPPORTED
    granted: FrozenSet[WindowStateFeature]

    @property
    def supported(self) -> bool:
        return bool(_valid_grants(self.granted))

    def allows(self, action: WindowStateAction) -> bool:
        try:
            feature = ACTION_FEATURE.get(action)
        except TypeError:
            return False
        return feature is not None and feature in _effective_grants(self)


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


# --- Window-reference guards -------------------------------------------------
#
# A state transition must not act on a recycled or foreign window instance.
# The registry stores only the current (owner, serial) generation per id: a
# destroyed id that is reused gets a new serial, so an old reference is stale
# without keeping an unbounded history of dead windows. Nothing here observes
# or drives a real window manager; the trusted host owns registration.

MAX_WINDOW_ID = 2_147_483_647
MAX_SERIAL = 2_147_483_647
MAX_LIVE_WINDOWS = 64
_OWNER = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")

REF_LIVE = "LIVE"
REF_STALE = "STALE"
REF_UNKNOWN = "UNKNOWN"
REF_UNAUTHORIZED = "UNAUTHORIZED"
REF_STATUSES = frozenset({REF_LIVE, REF_STALE, REF_UNKNOWN, REF_UNAUTHORIZED})

INVALID_REFERENCE = "INVALID_REFERENCE"
UNKNOWN_REFERENCE = "UNKNOWN_REFERENCE"
STALE_REFERENCE = "STALE_REFERENCE"
UNAUTHORIZED_REFERENCE = "UNAUTHORIZED_REFERENCE"
UNVALIDATED_REFERENCE = "UNVALIDATED_REFERENCE"

_REF_REJECTION = MappingProxyType({
    REF_STALE: STALE_REFERENCE,
    REF_UNKNOWN: UNKNOWN_REFERENCE,
    REF_UNAUTHORIZED: UNAUTHORIZED_REFERENCE,
})


class WindowReferenceError(ValueError):
    """Invalid registration, reference or bound; never a policy outcome."""


def _check_window_id(value):
    if type(value) is not int or not 1 <= value <= MAX_WINDOW_ID:
        raise WindowReferenceError("invalid window id")
    return value


def _check_serial(value):
    if type(value) is not int or not 1 <= value <= MAX_SERIAL:
        raise WindowReferenceError("invalid window serial")
    return value


def _check_owner(value):
    if type(value) is not str or not _OWNER.fullmatch(value):
        raise WindowReferenceError("invalid window owner")
    return value


@dataclass(frozen=True)
class WindowStateRef:
    """Opaque reference to one registered window instance and its owner."""

    window_id: int
    serial: int
    owner: str

    def __post_init__(self):
        _check_window_id(self.window_id)
        _check_serial(self.serial)
        _check_owner(self.owner)


class WindowStateRegistry:
    """Bounded map of live window instances to current owner/serial.

    No history, callbacks, clocks, threads or I/O. ``status`` is a pure read
    of the current generation, and every denial leaves the map unchanged.
    """

    __slots__ = ("_live", "_next_serial", "_max_windows")

    def __init__(self, max_windows=MAX_LIVE_WINDOWS):
        if (type(max_windows) is not int
                or not 1 <= max_windows <= MAX_LIVE_WINDOWS):
            raise WindowReferenceError("invalid live window bound")
        self._live = {}
        self._next_serial = 1
        self._max_windows = max_windows

    @property
    def live_count(self):
        return len(self._live)

    def register(self, window_id, owner):
        """Register one host-owned instance; reusing an id mints a new serial."""
        _check_window_id(window_id)
        _check_owner(owner)
        if window_id in self._live:
            raise WindowReferenceError("window id already registered")
        if len(self._live) >= self._max_windows:
            raise WindowReferenceError("live window limit reached")
        if self._next_serial > MAX_SERIAL:
            raise WindowReferenceError("window serial limit reached")
        serial = self._next_serial
        self._next_serial += 1
        self._live[window_id] = (owner, serial)
        return WindowStateRef(window_id, serial, owner)

    def unregister(self, window_id, owner):
        """Drop one instance; only its recorded owner may do so."""
        _check_window_id(window_id)
        _check_owner(owner)
        entry = self._live.get(window_id)
        if entry is None or entry[0] != owner:
            return False
        del self._live[window_id]
        return True

    def status(self, reference):
        """Classify a reference against the live generation, fail closed."""
        if not isinstance(reference, WindowStateRef):
            return REF_UNKNOWN
        entry = self._live.get(reference.window_id)
        if entry is None:
            return REF_UNKNOWN
        owner, serial = entry
        # The serial is the instance identity: a recycled id is stale even if
        # the new instance happens to have a different owner.
        if serial != reference.serial:
            return REF_STALE
        if owner != reference.owner:
            return REF_UNAUTHORIZED
        return REF_LIVE


class WindowStateController:
    """One-window state machine gated by negotiation and an optional reference.

    Slots and a single state field keep memory bounded: no history, timers or
    background work. Callers own any window handle; this class never touches it.

    A controller constructed without a registry keeps the original unbound
    behaviour. A controller constructed *with* a registry requires a fresh,
    authorized ``WindowStateRef`` on every ``allows``/``apply`` call; stale,
    unknown, forged or unvalidatable references are rejected before the
    feature and transition checks and never mutate state.
    """

    __slots__ = ("_negotiation", "_state", "_registry")

    def __init__(self, negotiation: Negotiation, registry=None):
        if not isinstance(negotiation, Negotiation):
            raise TypeError("negotiation must be a Negotiation")
        if registry is not None and not isinstance(registry, WindowStateRegistry):
            raise TypeError("registry must be a WindowStateRegistry or None")
        self._negotiation = negotiation
        self._state = WindowState.NORMAL
        self._registry = registry

    @property
    def state(self) -> WindowState:
        return self._state

    @property
    def negotiation(self) -> Negotiation:
        return self._negotiation

    @property
    def reference_registry(self):
        return self._registry

    def _reference_rejection(self, reference):
        """Reason why a reference may not drive a decision, or None if valid."""
        if not isinstance(reference, WindowStateRef):
            return INVALID_REFERENCE
        if self._registry is None:
            return UNVALIDATED_REFERENCE
        return _REF_REJECTION.get(self._registry.status(reference))

    def allows(self, action: WindowStateAction, reference=None) -> bool:
        if self._registry is not None and reference is None:
            return False
        if (reference is not None
                and self._reference_rejection(reference) is not None):
            return False
        return self._negotiation.allows(action)

    def apply(self, action: WindowStateAction,
              reference=None) -> TransitionResult:
        if self._registry is not None and reference is None:
            return TransitionResult("REJECTED", self._state, INVALID_REFERENCE)
        if reference is not None:
            rejection = self._reference_rejection(reference)
            if rejection is not None:
                return TransitionResult("REJECTED", self._state, rejection)
        try:
            feature = ACTION_FEATURE.get(action)
        except TypeError:
            feature = None
        if feature is None:
            return TransitionResult("REJECTED", self._state, "UNKNOWN_ACTION")

        if feature not in _effective_grants(self._negotiation):
            return TransitionResult("REJECTED", self._state, "FEATURE_NOT_GRANTED")

        next_state = VALID_TRANSITIONS.get((self._state, action))
        if next_state is None:
            return TransitionResult("REJECTED", self._state, "INVALID_TRANSITION")
        self._state = next_state
        return TransitionResult("OK", next_state)
