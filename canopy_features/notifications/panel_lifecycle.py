"""Bounded panel/session lifecycle notification contract at the trusted source.

This pure in-process module composes the existing host-owned
``TrustedHostEventSource`` with an explicit panel visibility lifecycle and the
existing protocol-v2 session observation vocabulary. It decides whether
trusted, already-projected notice rows may be *surfaced* to a Classic
notification panel; it never invents a notice, topic, payload field or id.

Trust boundary: only code holding the returned lifecycle object can publish
through its source or drive panel/host signals. QML and community Shell Packs
never construct an event, choose a payload field or extend this contract. The
initial view is fail closed: no session observation means no rows, and a closed
or obscured panel, a lost boundary, a lost source or a stale re-observation
never surfaces rows.

It creates no Qt object, notification daemon, socket, process, timer, poll,
thread, filesystem access or network connection. It performs no real session
change, compositor call or desktop announcement. This is NOT a compiled bridge,
live desktop notification, screen-reader behaviour, Linux Mint acceptance or
owner visual approval.

Existing contracts are reused, never extended: protocol v2 ``HostEvent`` and
its four topics from ``canopy_core.host_events``, the projected record shape
from ``canopy_features.notifications.host_event_source`` and
``host_snapshot_producer``, and the session status tokens from
``canopy_features.system.quick_controls_state``. No protocol version, topic,
payload field or status token is added here.
"""
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import islice
from types import MappingProxyType
from typing import Any, cast

from canopy_core.host_events import PROTOCOL_VERSION, HostEvent
from canopy_features.notifications.host_event_source import (
    MAX_ITEMS,
    SOURCE,
    TrustedHostEventSource,
)
from canopy_features.notifications.host_snapshot_producer import (
    compose,
    SnapshotProducerError,
)
from canopy_features.system.quick_controls_state import (
    STATUS_TOKENS,
    SESSION_TOPIC,
)

__all__ = [
    "AVAILABLE", "CLOSED", "MAX_BATCH", "MAX_HISTORY", "MAX_ITEMS",
    "PROTOCOL_VERSION", "SOURCE", "SESSION_TOPIC",
    "PANEL_CLOSED", "PANEL_OPEN", "PANEL_OBSCURED",
    "STATUS_ACTIVE", "STATUS_UNKNOWN", "SESSION_STATUS",
    "REASON_OK", "REASON_NO_OBSERVATION", "REASON_PANEL_CLOSED",
    "REASON_PANEL_OBSCURED", "REASON_SESSION_NOT_ACTIVE",
    "REASON_SOURCE_LOST", "REASON_BOUNDARY_LOST",
    "REASON_NEEDS_REOBSERVATION", "REASON_CLOSED",
    "DISCLOSURES", "UNAVAILABLE",
    "BatchResult", "PanelLifecycleError", "PanelSessionLifecycle",
]

# Callers may lower these ceilings, never raise them. Notice capacity is the
# trusted source's own bound: this layer never buffers more rows than the
# source itself can hold.
MAX_ITEMS = MAX_ITEMS
MAX_HISTORY = 12
MAX_BATCH = 32

PANEL_CLOSED = "closed"
PANEL_OPEN = "open"
# A locked/suspended observation must not leave an active panel showing
# pre-lock notices; the panel is obscured until an explicit recovery signal.
PANEL_OBSCURED = "obscured"
_PANEL_STATES = frozenset({PANEL_CLOSED, PANEL_OPEN, PANEL_OBSCURED})

SESSION_STATUS = frozenset(STATUS_TOKENS["session"])
STATUS_ACTIVE = "active"
STATUS_UNKNOWN = "unknown"
_PRIVILEGED_STATUSES = frozenset({"locked", "suspended"})

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"

REASON_OK = "ok"
REASON_NO_OBSERVATION = "no-session-observation"
REASON_PANEL_CLOSED = "panel-closed"
REASON_PANEL_OBSCURED = "panel-obscured"
REASON_SESSION_NOT_ACTIVE = "session-not-active"
REASON_SOURCE_LOST = "source-lost"
REASON_BOUNDARY_LOST = "boundary-lost"
REASON_NEEDS_REOBSERVATION = "needs-reobservation"
REASON_CLOSED = "lifecycle-closed"

# Fixed, caller-independent disclosures. No rejected payload, exception text
# or observed value is ever rendered into these strings.
DISCLOSURES = MappingProxyType({
    REASON_OK: "Available",
    REASON_NO_OBSERVATION: "Unavailable — no session observation",
    REASON_PANEL_CLOSED: "Unavailable — notification panel is closed",
    REASON_PANEL_OBSCURED: "Unavailable — panel obscured by session state",
    REASON_SESSION_NOT_ACTIVE: "Unavailable — session is not active",
    REASON_SOURCE_LOST: "Unavailable — trusted event source is no longer connected",
    REASON_BOUNDARY_LOST: "Unavailable — trusted host boundary is unavailable",
    REASON_NEEDS_REOBSERVATION: "Unavailable — session needs re-observation",
    REASON_CLOSED: "Unavailable — panel lifecycle is closed",
})


class PanelLifecycleError(ValueError):
    """Invalid caller input, wrong event type, or misuse after shutdown."""


@dataclass(frozen=True)
class BatchResult:
    """Bounded accounting for one ``publish_many`` call."""

    consumed: int
    accepted: int
    stopped: bool

    def __post_init__(self):
        for name in ("consumed", "accepted"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise PanelLifecycleError("invalid batch count")
        if type(self.stopped) is not bool or self.accepted > self.consumed:
            raise PanelLifecycleError("inconsistent batch result")

    def as_dict(self):
        return {"consumed": self.consumed, "accepted": self.accepted,
                "stopped": self.stopped}


class PanelSessionLifecycle:
    """Host-owned, single-thread view over one trusted host-event source.

    Panel visibility and host availability are explicit trusted signals, not
    host events: no event topic, payload field or protocol version is added.
    Every notice row in ``snapshot()`` originates in a real ``HostEvent``
    already delivered by the trusted source.
    """

    def __init__(self, *, source=None, max_items=MAX_ITEMS,
                 max_history=MAX_HISTORY, max_batch=MAX_BATCH):
        for name, value, ceiling in (("max_items", max_items, MAX_ITEMS),
                                     ("max_history", max_history, MAX_HISTORY),
                                     ("max_batch", max_batch, MAX_BATCH)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise PanelLifecycleError("invalid " + name + " bound")
        if source is None:
            self._source = TrustedHostEventSource(max_items=max_items)
            self._owns_source = True
        elif type(source) is TrustedHostEventSource and source.connected():
            self._source = source
            self._owns_source = False
        else:
            raise PanelLifecycleError("trusted connected host event source required")
        self._max_items = max_items
        self._max_history = max_history
        self._max_batch = max_batch
        self._panel = PANEL_CLOSED
        self._session = STATUS_UNKNOWN
        self._sequence = None
        self._boundary_ok = True
        self._needs_reobservation = False
        self._closed = False
        self._history = deque(maxlen=max_history)
        self._counts = dict(
            publishes=0, observations=0, stale=0, panel_opens=0,
            panel_closes=0, obscures=0, boundary_losses=0,
            reobservations=0, dropped=0,
        )

    # -- caller guards ---------------------------------------------------
    def _mutable(self):
        if self._closed:
            raise PanelLifecycleError("panel lifecycle is closed")
        if not self._boundary_ok:
            raise PanelLifecycleError("trusted host boundary is unavailable")

    @staticmethod
    def _check_event(event):
        # Exact type: a forged subclass cannot override ``payload`` and smuggle
        # an unvalidated session status into the panel view.
        if type(event) is not HostEvent:
            raise PanelLifecycleError("observation requires a HostEvent")
        if event.topic != SESSION_TOPIC:
            raise PanelLifecycleError("unsupported observation topic")
        if event.version != PROTOCOL_VERSION:
            raise PanelLifecycleError("unsupported event protocol version")
        if type(event.sequence) is not int or event.sequence < 0:
            raise PanelLifecycleError("invalid event sequence")

    def _lose_boundary(self, marker):
        """Fail closed: hide all rows and forget the active session view."""
        if self._boundary_ok:
            self._counts["boundary_losses"] += 1
            self._history.append(marker)
        self._boundary_ok = False
        self._needs_reobservation = True
        self._session = STATUS_UNKNOWN
        # Keep the last sequence: a late event from before the loss cannot
        # resurrect the old view after the boundary is restored.

    # -- trusted host signals -------------------------------------------
    def mark_host_unavailable(self):
        """Trusted signal that the event boundary can no longer be trusted."""
        if self._closed:
            raise PanelLifecycleError("panel lifecycle is closed")
        self._lose_boundary("host-unavailable")

    def restore_host(self):
        """Reopen intake only; rows stay hidden until re-observation + ack."""
        if self._closed:
            raise PanelLifecycleError("panel lifecycle is closed")
        if self._boundary_ok:
            return False
        self._boundary_ok = True
        self._history.append("host-restored")
        return True

    def acknowledge_reobservation(self):
        """Explicit trusted acknowledgement; never driven by an event alone."""
        self._mutable()
        if not self._needs_reobservation:
            return False
        self._needs_reobservation = False
        self._counts["reobservations"] += 1
        return True

    def open_panel(self):
        """Trusted presentation signal; returns True if the state changed."""
        self._mutable()
        if self._panel == PANEL_OPEN:
            return False
        if self._panel == PANEL_OBSCURED and self._needs_reobservation:
            raise PanelLifecycleError("obscured panel needs re-observation")
        self._panel = PANEL_OPEN
        self._counts["panel_opens"] += 1
        return True

    def close_panel(self):
        """Trusted presentation signal; hides rows without closing the bus."""
        if self._closed or self._panel == PANEL_CLOSED:
            return False
        self._panel = PANEL_CLOSED
        self._counts["panel_closes"] += 1
        return True

    def close(self):
        """Irreversible fail-closed cleanup; does not close an injected source."""
        if self._closed:
            return
        self._panel = PANEL_CLOSED
        self._session = STATUS_UNKNOWN
        self._needs_reobservation = False
        self._counts["panel_closes"] += 1
        self._closed = True
        self._history.append("closed")
        if self._owns_source:
            self._source.close()

    # -- intake and folding ---------------------------------------------
    def publish(self, topic, payload):
        """Host-only delivery of one real event into the trusted bus."""
        self._mutable()
        try:
            result = self._source.emit(topic, payload)
        except (ValueError, TypeError, RuntimeError, UnicodeError) as exc:
            raise PanelLifecycleError("host event refused") from exc
        self._counts["publishes"] += 1
        if topic == SESSION_TOPIC:
            self._fold(result.event)
        return result

    def observe(self, event):
        """Fold an already-delivered real ``HostEvent`` (no second emission)."""
        self._mutable()
        try:
            self._check_event(event)
        except PanelLifecycleError:
            self._lose_boundary("invalid-observation")
            raise
        self._fold(event)
        return self.view()

    def publish_many(self, items):
        """Consume at most ``max_batch`` host-only (topic, payload) pairs."""
        self._mutable()
        if (isinstance(items, (str, bytes, bytearray, Mapping))
                or not isinstance(items, Iterable)):
            raise PanelLifecycleError("publish batch must be an iterable")
        consumed = accepted = 0
        stopped = False
        for item in islice(items, self._max_batch):
            consumed += 1
            if (type(item) is not tuple or len(item) != 2
                    or type(item[0]) is not str):
                raise PanelLifecycleError("invalid publish batch item")
            try:
                self.publish(item[0], item[1])
            except PanelLifecycleError:
                stopped = True
                break
            accepted += 1
        return BatchResult(consumed, accepted, stopped)

    def _fold(self, event):
        """Fold one real session event into the bounded panel/session view."""
        if self._sequence is not None and event.sequence <= self._sequence:
            self._counts["stale"] += 1
            return False
        try:
            payload = event.payload
            status = payload.get("state") if isinstance(payload, Mapping) else None
        except Exception:
            self._lose_boundary("invalid-observation")
            raise PanelLifecycleError("invalid session observation") from None
        if type(status) is not str or status not in SESSION_STATUS:
            self._lose_boundary("invalid-session-observation")
            raise PanelLifecycleError("invalid session observation")
        previous = self._session
        self._sequence = event.sequence
        self._session = status
        self._counts["observations"] += 1
        if status in _PRIVILEGED_STATUSES:
            self._needs_reobservation = True
            if self._panel == PANEL_OPEN:
                self._panel = PANEL_OBSCURED
                self._counts["obscures"] += 1
                self._history.append("obscured")
        elif status == STATUS_ACTIVE and previous in _PRIVILEGED_STATUSES:
            self._needs_reobservation = True
        return True

    # -- projection ------------------------------------------------------
    @property
    def status(self):
        return AVAILABLE if self._surfacing() else UNAVAILABLE

    @property
    def reason(self):
        if self._closed:
            return REASON_CLOSED
        if not self._boundary_ok:
            return REASON_BOUNDARY_LOST
        if not self._source.connected():
            return REASON_SOURCE_LOST
        if self._panel == PANEL_OBSCURED:
            return REASON_PANEL_OBSCURED
        if self._needs_reobservation:
            return REASON_NEEDS_REOBSERVATION
        if self._session == STATUS_UNKNOWN:
            return REASON_NO_OBSERVATION
        if self._panel != PANEL_OPEN:
            return REASON_PANEL_CLOSED
        if self._session != STATUS_ACTIVE:
            return REASON_SESSION_NOT_ACTIVE
        return REASON_OK

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    def _surfacing(self):
        return self.reason == REASON_OK

    def view(self):
        """Immutable deterministic projection with fixed key order."""
        surfacing = self._surfacing()
        records = ()
        if surfacing:
            try:
                snapshot = compose(self._source.snapshot(),
                                   max_records=self._max_items)
            except (SnapshotProducerError, ValueError, TypeError, RuntimeError):
                self._lose_boundary("invalid-source-record")
                surfacing = False
            else:
                records = tuple(MappingProxyType(dict(record.as_dict()))
                                for record in snapshot.records)
        reason = self.reason
        surfacing = surfacing and reason == REASON_OK
        if not surfacing:
            records = ()
        self._counts["dropped"] = self._source.dropped_count
        return MappingProxyType({
            "source": SOURCE,
            "panel": self._panel,
            "session": self._session,
            "sequence": self._sequence,
            "boundary": "available" if self._boundary_ok else "unavailable",
            "closed": self._closed,
            "needs_reobservation": self._needs_reobservation,
            "surfacing": surfacing,
            "status": AVAILABLE if surfacing else UNAVAILABLE,
            "reason": reason,
            "disclosure": DISCLOSURES[reason],
            "records": records,
            "history": tuple(self._history),
            "counts": MappingProxyType(dict(self._counts)),
        })

    def snapshot(self):
        return self.view()

    def to_dict(self):
        """JSON-friendly copy; never exposes live internal containers."""
        view = cast(Mapping[str, Any], self.view())
        return {
            "source": view["source"],
            "panel": view["panel"],
            "session": view["session"],
            "sequence": view["sequence"],
            "boundary": view["boundary"],
            "closed": view["closed"],
            "needs_reobservation": view["needs_reobservation"],
            "surfacing": view["surfacing"],
            "status": view["status"],
            "reason": view["reason"],
            "disclosure": view["disclosure"],
            "records": [dict(record) for record in view["records"]],
            "history": list(view["history"]),
            "counts": dict(view["counts"]),
        }
