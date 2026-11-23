"""Pure, bounded dock running-indicator state derived from trusted app events.

The module never observes the desktop, spawns processes, polls, draws controls
or changes any approved visual element. Callers feed it trusted lifecycle
events; it returns immutable state from which a dock adapter may later derive
an indicator. All collections are bounded and event order is explicit.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_APPS = 64
MAX_PIDS_PER_APP = 8
MAX_PID = 2**31 - 1
MAX_ID_LENGTH = 128


@dataclass(frozen=True)
class AppStarted:
    sequence: int
    app_id: str
    pid: int


@dataclass(frozen=True)
class AppExited:
    sequence: int
    app_id: str
    pid: int


Event = AppStarted | AppExited


@dataclass(frozen=True)
class IndicatorState:
    """Immutable, sequence-stamped mapping of live process IDs to app IDs."""

    sequence: int
    owners: tuple[tuple[int, str], ...]


def empty_state() -> IndicatorState:
    return IndicatorState(sequence=-1, owners=())


def _validate(event: Event) -> None:
    if not isinstance(event, (AppStarted, AppExited)):
        raise ValueError("unsupported event type")
    if isinstance(event.sequence, bool) or not isinstance(event.sequence, int):
        raise ValueError("sequence must be an integer")
    if event.sequence < 0:
        raise ValueError("sequence must be non-negative")
    if not isinstance(event.app_id, str) or not event.app_id or \
            len(event.app_id) > MAX_ID_LENGTH:
        raise ValueError("invalid app_id")
    if isinstance(event.pid, bool) or not isinstance(event.pid, int) or \
            not 1 <= event.pid <= MAX_PID:
        raise ValueError("invalid pid")


def apply_event(state: IndicatorState, event: Event) -> IndicatorState:
    """Apply one trusted event; stale, duplicate and overflow events are ignored.

    Ignoring (rather than raising) keeps an event-driven consumer alive when a
    compositor emits duplicate, late or excessive notifications. Every
    accepted-or-ignored event still advances the sequence, so old events cannot
    be replayed later to mutate the indicator state.
    """
    if not isinstance(state, IndicatorState):
        raise ValueError("state must be an IndicatorState")
    _validate(event)
    if event.sequence <= state.sequence:
        return state

    owners = dict(state.owners)
    if isinstance(event, AppStarted):
        previous = owners.get(event.pid)
        if previous is not None and previous != event.app_id:
            # PID reuse: the old owner no longer controls this process.
            del owners[event.pid]
        elif previous == event.app_id:
            owners = dict(state.owners)
            return IndicatorState(sequence=event.sequence,
                                  owners=tuple(sorted(owners.items())))
        pid_count = sum(1 for owner in owners.values() if owner == event.app_id)
        app_count = len(set(owners.values()) | {event.app_id})
        if pid_count >= MAX_PIDS_PER_APP or app_count > MAX_APPS:
            return IndicatorState(sequence=event.sequence, owners=state.owners)
        owners[event.pid] = event.app_id
    else:
        if owners.get(event.pid) != event.app_id:
            return IndicatorState(sequence=event.sequence, owners=state.owners)
        del owners[event.pid]

    return IndicatorState(sequence=event.sequence, owners=tuple(sorted(owners.items())))


def apply_events(state: IndicatorState, events) -> IndicatorState:
    """Fold a bounded batch of trusted events in arrival order."""
    if isinstance(events, (str, bytes)) or not isinstance(events, (list, tuple)):
        raise ValueError("events must be a sequence")
    if len(events) > 1024:
        raise ValueError("too many events")
    current = state
    for event in events:
        current = apply_event(current, event)
    return current


def indicator_ids(state: IndicatorState) -> tuple[str, ...]:
    """Return sorted identifiers with at least one live process."""
    if not isinstance(state, IndicatorState):
        raise ValueError("state must be an IndicatorState")
    return tuple(sorted({app_id for _, app_id in state.owners}))


def has_indicator(state: IndicatorState, app_id: str) -> bool:
    if not isinstance(app_id, str):
        raise ValueError("app_id must be a string")
    return app_id in indicator_ids(state)


def running_pid_count(state: IndicatorState, app_id: str) -> int:
    if not isinstance(app_id, str):
        raise ValueError("app_id must be a string")
    return sum(1 for _, owner in state.owners if owner == app_id)
