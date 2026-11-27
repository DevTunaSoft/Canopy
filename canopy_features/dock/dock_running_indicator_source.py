"""Bounded dock running-indicator source contract from trusted window-state events.

This is a pure, in-process composition layer. A trusted host adapter feeds it
window-state events that a real source has already observed and classified; the
module projects the eligible ones into the ``AppStarted`` / ``AppExited``
events consumed by :mod:`canopy_features.dock.dock_running_indicators` and
returns one immutable indicator state.

Trust boundary and non-overlap:
- No window manager, compositor, Qt/QML, desktop observation, process launch,
  socket, thread, timer, clock, environment read or file I/O. Nothing here
  observes a real window or draws an indicator.
- Window-reference validation (LIVE/STALE/UNKNOWN/UNAUTHORIZED) belongs to the
  already-merged ``canopy_features.windows.window_state_capabilities``
  contract (PR688). This module imports those status tokens and **consumes**
  the caller's classification; it does not register, resolve or authorize
  window references and never touches that module's registry.
- Workspace membership and identity belong to the PE-086 workspace contracts.
  This module consumes only the owner app id carried by a trusted event and
  never reads, imports or emits a workspace record.

Only events classified ``REF_LIVE`` may affect indicator state. Stale, unknown
and unauthorized references, out-of-order events and malformed inputs are
dropped fail closed. Every batch is bounded; equal inputs produce equal bytes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from canopy_features.dock import dock_running_indicators as indicators
from canopy_features.windows.window_state_capabilities import (
    REF_LIVE,
    REF_STALE,
    REF_UNKNOWN,
    REF_UNAUTHORIZED,
)

SOURCE = "window-state"
MAX_EVENTS = 1024
MAX_SEQUENCE = 2_147_483_647
MAX_WINDOW_ID = 2_147_483_647
MAX_APP_ID_LENGTH = indicators.MAX_ID_LENGTH
MAX_PID = indicators.MAX_PID

# Exact status vocabulary of the trusted window-state source. Importing the
# tokens (rather than redefining them) keeps this projection tied to the
# already-verified PR688 contract without duplicating its validation logic.
VALID_STATUSES = frozenset({REF_LIVE, REF_STALE, REF_UNKNOWN, REF_UNAUTHORIZED})
_APP_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")

if len(VALID_STATUSES) != 4 or REF_LIVE != "LIVE":  # pragma: no cover
    raise RuntimeError("window-state status contract changed; source must be reviewed")


class SourceContractError(ValueError):
    """Malformed, unbounded or untrusted window-state source input."""


@dataclass(frozen=True)
class WindowStateEvent:
    """One trusted, already-classified window-state event.

    ``sequence`` is the source's monotonic event sequence, ``status`` is the
    window-reference status the trusted source already computed, ``app_id`` is
    the window owner, ``pid`` is the owner process, ``window_id`` is the trusted
    window instance and ``opened`` is True when the window appeared. Callers
    supply these facts; the module neither discovers nor invents them.
    """

    sequence: int
    status: str
    app_id: str
    pid: int
    window_id: int
    opened: bool


@dataclass(frozen=True)
class Projection:
    """Immutable result of projecting one bounded event batch."""

    sequence: int
    events: tuple
    ignored: int
    indicators: indicators.IndicatorState

    def indicator_ids(self):
        """Sorted app ids with at least one live owner process."""
        return indicators.indicator_ids(self.indicators)


def _validate_event(event):
    if type(event) is not WindowStateEvent:
        raise SourceContractError("event must be a WindowStateEvent")
    if type(event.sequence) is not int or not 0 <= event.sequence <= MAX_SEQUENCE:
        raise SourceContractError("invalid event sequence")
    # Type-check before membership: an unhashable status container must fail
    # closed with the domain error, never leak a raw TypeError.
    if type(event.status) is not str or event.status not in VALID_STATUSES:
        raise SourceContractError("invalid window reference status")
    if (type(event.app_id) is not str
            or len(event.app_id) > MAX_APP_ID_LENGTH
            or not _APP_ID.fullmatch(event.app_id)):
        raise SourceContractError("invalid owner app id")
    # type(...) is int excludes bool, so no separate bool guard is needed.
    if type(event.pid) is not int or not 1 <= event.pid <= MAX_PID:
        raise SourceContractError("invalid owner pid")
    if type(event.window_id) is not int or not 1 <= event.window_id <= MAX_WINDOW_ID:
        raise SourceContractError("invalid window id")
    if type(event.opened) is not bool:
        raise SourceContractError("opened must be a bool")


def project(state, events):
    """Project a bounded batch of trusted window-state events onto indicators.

    ``state`` is an ``IndicatorState`` (normally ``empty_state()`` on the first
    call). Only ``REF_LIVE`` events with a strictly newer sequence become
    indicator events; all other events are counted as ignored. Every event with
    a newer sequence advances the projection sequence, matching the state
    model's replay-protection rule. One validated batch builds at most one new
    indicator state; a rejected input raises ``SourceContractError`` and leaves
    the caller's state untouched.
    """
    if isinstance(events, (str, bytes)) or type(events) not in (list, tuple):
        raise SourceContractError("events must be a bounded list or tuple")
    if len(events) > MAX_EVENTS:
        raise SourceContractError("too many window-state events")
    # Public validator: raises the indicator module's domain error for any
    # state that is not a genuine IndicatorState.
    indicators.indicator_ids(state)

    sequence = state.sequence
    projected = []
    ignored = 0
    for event in events:
        _validate_event(event)
        if event.sequence <= sequence:
            ignored += 1
            continue
        sequence = event.sequence
        if event.status != REF_LIVE:
            # Stale/unknown/unauthorized refs are dropped here, not validated
            # here: the trusted source already classified them.
            ignored += 1
            continue
        if event.opened:
            projected.append(indicators.AppStarted(
                sequence, event.app_id, event.pid))
        else:
            projected.append(indicators.AppExited(
                sequence, event.app_id, event.pid))

    next_state = indicators.apply_events(state, projected) if projected else state
    return Projection(sequence=sequence, events=tuple(projected),
                      ignored=ignored, indicators=next_state)


def apply_window_events(state, events):
    """Return only the resulting indicator state for one bounded batch."""
    return project(state, events).indicators


__all__ = [
    "SOURCE", "MAX_EVENTS", "MAX_SEQUENCE", "MAX_WINDOW_ID",
    "MAX_APP_ID_LENGTH", "MAX_PID", "VALID_STATUSES", "REF_LIVE",
    "SourceContractError", "WindowStateEvent", "Projection",
    "project", "apply_window_events",
]
