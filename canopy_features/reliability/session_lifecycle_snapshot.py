"""Bounded, immutable, host-facing session-lifecycle snapshot.

Composes three already-tested, independent state models into one deterministic
record:

* ``reliability/lock_session_events.py`` -- the bounded power/lock event
  reconciler, its fail-closed ``SessionState`` and recent transition history;
* ``reliability/theme_transition_rollback.py`` -- the offline ownership ledger
  for presentation resources during a theme switch, through its frozen
  ``Snapshot`` projection;
* ``windows/focus_intents.py`` -- the deny-by-default focus broker and its
  bounded decision history, plus an optional explicit ``PermissionPolicy``.

The snapshot is a pure composition layer: no I/O, clock, randomness, threads,
polling, OS observation, Qt or QML. The caller hands it the objects it already
owns; this module never asks the host for anything. Embedded collections are
bounded (recent decision lists, abandoned resource names, text fields), every
public view is immutable, and two compositions of equal inputs are
byte-for-byte identical. Every component is validated before any record is
built, so a rejected input raises ``SnapshotError`` without a partial result.

This is evidence-shaped bookkeeping, not proof of a running desktop. Real
power/lock events are always reported as ``NOT_PERFORMED`` and Mint, Qt and
visual acceptance as ``NOT_ESTABLISHED``. No caller input can turn this record
into an observation or acceptance claim.
"""

from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.lock_session_events import (
    DEFERRED, DUPLICATE, REDUNDANT, STALE, TRANSITION,
    Outcome, Reconciler, SessionState)
from canopy_features.reliability.theme_transition_rollback import (
    IDLE, PREPARED, Snapshot, ThemeTransitionRollback)
from canopy_features.windows.focus_intents import (
    ACTIVATION_FAILED, DENIED, GRANTED, STALE_TARGET, UNKNOWN_TARGET,
    FocusBroker, FocusDecision, PermissionPolicy)

SCHEMA = 1
MAX_RECENT = 8
MAX_THEME_NAMES = 16
MAX_CHARS = 160

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
EVENT_OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"

SESSION_LABELS = frozenset({"suspended", "locked", "active"})
SESSION_STATUSES = frozenset({TRANSITION, DUPLICATE, STALE, REDUNDANT, DEFERRED})
THEME_STATES = frozenset({IDLE, PREPARED})
FOCUS_STATUSES = frozenset({
    GRANTED, DENIED, STALE_TARGET, UNKNOWN_TARGET, ACTIVATION_FAILED})
FOCUS_FAILURE_STATUSES = frozenset({
    DENIED, STALE_TARGET, UNKNOWN_TARGET, ACTIVATION_FAILED})


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class SessionView:
    """Bounded projection of a lock/session reconciler."""

    label: str
    suspended: bool
    locked: bool
    accepted: int
    recent_statuses: tuple


@dataclass(frozen=True)
class ThemeView:
    """Bounded projection of a theme rollback ledger snapshot."""

    state: str
    active: object
    candidate: object
    single_owner: bool
    live_resource_count: int
    abandoned: tuple


@dataclass(frozen=True)
class FocusView:
    """Bounded projection of a focus broker and optional permission policy."""

    live_windows: int
    grant_count: object
    recent_statuses: tuple


@dataclass(frozen=True)
class SessionLifecycleSnapshot:
    """One deterministic, immutable record of host session-lifecycle state."""

    schema: int
    status: str
    acceptance: str
    event_observation: str
    session: SessionView
    theme: ThemeView
    focus: FocusView

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED

    def to_dict(self):
        """Return a fresh read-only view with a fixed, stable key order."""
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "acceptance": self.acceptance,
            "event_observation": self.event_observation,
            "session": MappingProxyType({
                "label": self.session.label,
                "suspended": self.session.suspended,
                "locked": self.session.locked,
                "accepted": self.session.accepted,
                "recent_statuses": self.session.recent_statuses,
            }),
            "theme": MappingProxyType({
                "state": self.theme.state,
                "active": self.theme.active,
                "candidate": self.theme.candidate,
                "single_owner": self.theme.single_owner,
                "live_resource_count": self.theme.live_resource_count,
                "abandoned": self.theme.abandoned,
            }),
            "focus": MappingProxyType({
                "live_windows": self.focus.live_windows,
                "grant_count": self.focus.grant_count,
                "recent_statuses": self.focus.recent_statuses,
            }),
        })


def _flag(value, field):
    if type(value) is not bool:
        raise SnapshotError(field + " must be a bool")
    return value


def _count(value, field):
    if type(value) is not int or value < 0:
        raise SnapshotError(field + " must be a non-negative int")
    return value


def _text(value, field):
    if type(value) is not str:
        raise SnapshotError(field + " must be a string")
    return value


def _bounded_text(value, field):
    return _text(value, field)[:MAX_CHARS]


def _optional_name(value, field):
    if value is None:
        return None
    return _bounded_text(value, field)


def _statuses(values, allowed, field, record_type):
    if type(values) is not tuple:
        raise SnapshotError(field + " must be a tuple")
    result = []
    for value in values[-MAX_RECENT:]:
        if not isinstance(value, record_type):
            raise SnapshotError(field + " must hold "
                                + record_type.__name__ + " entries")
        status = _text(value.status, field + " status")
        if status not in allowed:
            raise SnapshotError("unsupported " + field + " status")
        result.append(status)
    return tuple(result)


def _focus_statuses(values):
    """Validate focus history statuses and their reason fields together.

    The broker records a reason only on DENIED/ACTIVATION_FAILED decisions.
    A GRANTED decision carrying one is a contradictory record: it would let
    ``_derive_status`` claim a ready/safe session from a failed focus
    decision. Validate the durable reason field even though the snapshot does
    not project it, so hostile-but-bounded text cannot manufacture that claim
    and a non-string reason cannot escape as a raw exception.
    """
    statuses = _statuses(values, FOCUS_STATUSES, "focus history", FocusDecision)
    for decision, status in zip(values[-MAX_RECENT:], statuses):
        reason = _bounded_text(getattr(decision, "reason", ""),
                               "focus decision reason")
        if status == GRANTED and reason:
            raise SnapshotError("granted focus decision carries a reason")
    return statuses


def _session_view(reconciler):
    if not isinstance(reconciler, Reconciler):
        raise SnapshotError("session must be a Reconciler")
    state = reconciler.state
    if not isinstance(state, SessionState):
        raise SnapshotError("session state must be a SessionState")
    suspended = _flag(state.suspended, "session suspended")
    locked = _flag(state.locked, "session locked")
    label = _text(state.label, "session label")
    if label not in SESSION_LABELS:
        raise SnapshotError("unknown session state label")
    expected = "suspended" if suspended else ("locked" if locked else "active")
    if label != expected:
        raise SnapshotError("session state label disagrees with its flags")
    accepted = _count(reconciler.accepted, "session accepted count")
    return SessionView(
        label=label,
        suspended=suspended,
        locked=locked,
        accepted=accepted,
        recent_statuses=_statuses(reconciler.history, SESSION_STATUSES,
                                  "session history", Outcome),
    )


def _theme_view(ledger):
    if not isinstance(ledger, ThemeTransitionRollback):
        raise SnapshotError("theme must be a ThemeTransitionRollback")
    projected = ledger.snapshot()
    if not isinstance(projected, Snapshot):
        raise SnapshotError("theme projection must be a Snapshot")
    state = _text(projected.state, "theme state")
    if state not in THEME_STATES:
        raise SnapshotError("unsupported theme state")
    single_owner = _flag(projected.single_owner, "theme single-owner flag")
    live = projected.live_resources
    abandoned = projected.abandoned_resources
    if type(live) is not frozenset or type(abandoned) is not frozenset:
        raise SnapshotError("theme resource sets must be frozensets")
    for name in live:
        _bounded_text(name, "live resource name")
    names = [_bounded_text(name, "abandoned resource name")
             for name in abandoned]
    if len(names) > MAX_THEME_NAMES:
        raise SnapshotError("abandoned resource set exceeds snapshot bound")
    if single_owner != (not (live & abandoned)):
        raise SnapshotError("single-owner flag disagrees with resource sets")
    # The ledger's invariant is IDLE <=> no in-flight candidate. A hostile
    # snapshot that claims IDLE while carrying a candidate would let
    # ``_derive_status`` return STATUS_OK for a switch that never committed.
    active = _optional_name(projected.active, "theme active")
    candidate = _optional_name(projected.candidate, "theme candidate")
    if (state == IDLE) != (candidate is None):
        raise SnapshotError("theme state disagrees with its candidate")
    return ThemeView(
        state=state,
        active=active,
        candidate=candidate,
        single_owner=single_owner,
        live_resource_count=len(live),
        abandoned=tuple(sorted(names)),
    )


def _focus_view(broker, policy):
    if not isinstance(broker, FocusBroker):
        raise SnapshotError("focus must be a FocusBroker")
    if policy is not None and not isinstance(policy, PermissionPolicy):
        raise SnapshotError("policy must be a PermissionPolicy or None")
    return FocusView(
        live_windows=_count(broker.live_window_count, "focus live window count"),
        grant_count=(None if policy is None
                     else _count(policy.grant_count, "focus grant count")),
        recent_statuses=_focus_statuses(broker.history),
    )


def _derive_status(session, theme, focus):
    # A non-active session, an uncommitted theme switch, double-owned
    # resources or any failed focus decision blocks the record; these outrank
    # the softer attention conditions. Abandoned handles awaiting disposal,
    # recorded session churn, cross-app focus grants and a non-empty focus
    # history are attention-worthy but leave the snapshot usable. This status
    # describes only the supplied state, never a running desktop.
    if (session.label != "active"
            or theme.state == PREPARED
            or not theme.single_owner
            or any(status in FOCUS_FAILURE_STATUSES
                   for status in focus.recent_statuses)):
        return STATUS_BLOCKED
    if (theme.abandoned
            or session.recent_statuses
            or focus.grant_count
            or any(status != GRANTED for status in focus.recent_statuses)):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(session, theme, focus, policy=None):
    """Compose three already-tested state models into one immutable record.

    Every component is validated before any record is built, so a rejected
    input raises ``SnapshotError`` without leaking a partial snapshot. The
    source objects are never mutated. ``policy`` is optional; omitting it
    records ``grant_count`` as ``None`` rather than assuming a policy exists.
    """
    session_view = _session_view(session)
    theme_view = _theme_view(theme)
    focus_view = _focus_view(focus, policy)
    return SessionLifecycleSnapshot(
        schema=SCHEMA,
        status=_derive_status(session_view, theme_view, focus_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        event_observation=EVENT_OBSERVATION_NOT_PERFORMED,
        session=session_view,
        theme=theme_view,
        focus=focus_view,
    )
