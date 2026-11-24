"""Read-only, lazy Shell Host-facing adapter for validated focus decisions.

This module is a thin boundary over ``canopy_features.windows.focus_intents``.
It exposes stable value types and a decision-only API so a trusted host can ask
"would this focus request be allowed?" without importing policy code at startup.

Scope and limits:
- The validated policy module is imported on first use, never at module import.
- Only trusted host code may build an adapter: construction needs both an
  opaque :class:`HostAuthority` issued by :func:`issue_host_authority` and an
  explicit ``authorize`` callback. Metadata, QML, pack paths and string IDs
  can never construct one. This is an in-process trust boundary, not a sandbox.
- The only backend consulted is ``authorize``. No ``activate`` callback is
  ever supplied, so this adapter cannot change window focus, launch an
  application, query the compositor or touch the OS. Decisions are advisory.
- Every request is single-use; replays are rejected without consulting the
  backend. Consumed-request bookkeeping is bounded and deterministic.
- No Qt, compositor, X11/Wayland, D-Bus, sockets, threads, timers or polling.
  State is process-local. This is not permission enforcement or proof of a
  running shell.
"""

from collections import deque
from dataclasses import dataclass, field
import importlib
from typing import Callable, Optional

ADAPTER_VERSION = 1
FOCUS_MODULE = "canopy_features.windows.focus_intents"

# Mirrors of the validated pure module's public statuses. Defined here so host
# callers depend on this module's stable contract, not on policy internals.
GRANTED = "GRANTED"
DENIED = "DENIED"
STALE_TARGET = "STALE_TARGET"
UNKNOWN_TARGET = "UNKNOWN_TARGET"
ACTIVATION_FAILED = "ACTIVATION_FAILED"
REJECTED = "REJECTED"       # adapter boundary rejection, never a policy result
REPLAYED = "REPLAYED"       # duplicate decision request, never a policy result

# Local mirrors of validated bounds; the pure module remains the authority.
MAX_LIVE_WINDOWS = 256
MAX_REPLAY_WINDOW = 64

_SEAL = object()


class AdapterTrustError(PermissionError):
    """Construction was not requested by explicitly trusted host code."""


class AdapterInputError(ValueError):
    """A caller supplied malformed input; never a policy outcome."""


class HostAuthority:
    """Opaque capability minted only by :func:`issue_host_authority`."""

    __slots__ = ("_seal",)

    def __init__(self, seal):
        if seal is not _SEAL:
            raise AdapterTrustError("host authority must be issued explicitly")
        self._seal = seal


def issue_host_authority():
    """Issue the opaque token required to construct a focus adapter.

    Only application/host startup code should call this. It is an in-process
    convention for separating reviewed host code from untrusted inputs; it is
    not a security boundary against code already running in the process.
    """
    return HostAuthority(_SEAL)


@dataclass(frozen=True, slots=True)
class WindowHandle:
    """Opaque reference to one observed window instance."""

    window_id: int
    serial: int
    _tag: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class FocusRequest:
    """Single-use decision request issued by one adapter instance."""

    request_id: int
    origin_app: str
    handle: WindowHandle
    _tag: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class FocusDecisionView:
    """Stable, immutable host-facing view of one focus decision."""

    status: str
    origin_app: str
    target_window_id: Optional[int]
    target_app: Optional[str]
    allowed: bool
    reason: str


class WindowFocusAdapter:
    """Decision-only facade over the validated focus-intent broker.

    The host supplies observed windows and an ``authorize`` callable. This
    facade records decisions but performs none of them.
    """

    def __init__(self, authority, authorize: Callable[[str, str], bool], *,
                 max_live_windows=None):
        if not isinstance(authority, HostAuthority) or authority._seal is not _SEAL:
            raise AdapterTrustError("explicit host authority required")
        if not callable(authorize):
            raise AdapterTrustError("explicit authorize backend required")
        if max_live_windows is not None and (
                type(max_live_windows) is not int
                or not 1 <= max_live_windows <= MAX_LIVE_WINDOWS):
            raise AdapterInputError("invalid live window bound")
        self._authorize = authorize
        self._max_live_windows = max_live_windows
        self._focus = None
        self._broker = None
        self._tag = object()
        self._next_request_id = 1
        self._consumed = deque(maxlen=MAX_REPLAY_WINDOW)
        self._consumed_ids = set()
        self._replay_floor = 0
        self._decisions = 0
        self._rejections = 0
        self._replays = 0

    @property
    def protocol_version(self):
        return ADAPTER_VERSION

    @property
    def module_loaded(self):
        """True once the validated policy module has actually been imported."""
        return self._focus is not None

    @property
    def decision_count(self):
        return self._decisions

    @property
    def rejection_count(self):
        return self._rejections

    @property
    def replay_count(self):
        return self._replays

    @property
    def live_window_count(self):
        return 0 if self._broker is None else self._broker.live_window_count

    def _module(self):
        if self._focus is None:
            focus = importlib.import_module(FOCUS_MODULE)
            if focus.PROTOCOL_VERSION != 1:
                raise AdapterTrustError("unsupported focus policy version")
            self._focus = focus
        return self._focus

    def _get_broker(self):
        if self._broker is None:
            focus = self._module()
            bounds = ({}
                      if self._max_live_windows is None
                      else {"max_live_windows": self._max_live_windows})
            # No activate callback: the pure module can decide, never act.
            self._broker = focus.FocusBroker(self._authorize, None, **bounds)
        return self._broker

    def _valid_handle(self, handle):
        return type(handle) is WindowHandle and handle._tag is self._tag

    def _view(self, status, origin_app, window_id, target_app, allowed, reason):
        return FocusDecisionView(status, origin_app, window_id,
                                 target_app, allowed, reason)

    def _reject(self, origin_app, window_id, reason):
        self._rejections += 1
        return self._view(REJECTED, origin_app, window_id, None, False, reason)

    def observe_window(self, app_id, window_id):
        """Record a host-reported window snapshot; return an opaque handle."""
        focus = self._module()
        try:
            ref = self._get_broker().register_window(app_id, window_id)
        except focus.FocusIntentError as exc:
            raise AdapterInputError(str(exc)) from None
        return WindowHandle(ref.window_id, ref.serial, self._tag)

    def forget_window(self, handle):
        """Drop a host-reported window snapshot. Returns whether one existed."""
        if not self._valid_handle(handle):
            raise AdapterInputError("untrusted window handle")
        return self._get_broker().unregister_window(handle.window_id)

    def issue_request(self, origin_app, handle):
        """Create a single-use request. Reuses the policy module's validation."""
        if not self._valid_handle(handle):
            raise AdapterInputError("untrusted window handle")
        focus = self._module()
        try:
            focus.FocusIntent(origin_app,
                              focus.WindowRef(handle.window_id, handle.serial))
        except focus.FocusIntentError as exc:
            raise AdapterInputError(str(exc)) from None
        request_id = self._next_request_id
        self._next_request_id += 1
        return FocusRequest(request_id, origin_app, handle, self._tag)

    def _consume(self, request_id):
        if len(self._consumed) == self._consumed.maxlen:
            evicted = self._consumed.popleft()
            self._consumed_ids.discard(evicted)
            self._replay_floor = max(self._replay_floor, evicted)
        self._consumed.append(request_id)
        self._consumed_ids.add(request_id)

    def decide(self, request):
        """Return a stable decision without changing any window or app."""
        self._decisions += 1
        if type(request) is not FocusRequest or request._tag is not self._tag:
            return self._reject("", None, "untrusted request")
        origin_app = request.origin_app
        window_id = request.handle.window_id
        if request.request_id < 1 or request.request_id >= self._next_request_id:
            return self._reject(origin_app, window_id, "unissued request")
        if (request.request_id <= self._replay_floor
                or request.request_id in self._consumed_ids):
            self._replays += 1
            return self._view(REPLAYED, origin_app, window_id, None, False,
                              "request already decided")

        self._consume(request.request_id)
        focus = self._module()
        try:
            intent = focus.FocusIntent(
                origin_app,
                focus.WindowRef(window_id, request.handle.serial))
            decision = self._get_broker().request_focus(intent)
        except focus.FocusIntentError:
            return self._reject(origin_app, window_id, "invalid request")
        return self._view(decision.status, origin_app, window_id,
                          decision.target_app, decision.allowed, decision.reason)
