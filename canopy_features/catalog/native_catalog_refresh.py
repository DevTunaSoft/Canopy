"""Bounded native catalog refresh bridge for Classic's launcher availability.

This is a pure in-process adapter. It consumes only the existing protocol-v2
``app.catalog.changed`` host event topic, re-produces the native catalog from
the one explicit applications directory already used by
:mod:`canopy_features.launcher.native_catalog_producer`, and feeds authoritative
install/remove observations into an existing
:class:`~canopy_features.catalog.missing_app_availability.MissingAppTracker`.
It does not extend the host-event contract, create events, start a process,
open a shell, poll, keep a timer, spawn a thread, touch the network, modify the
catalog source or change any visual state.

Every refusal is fail closed and atomic: the previous wire snapshot and the
previous availability states stay byte-identical, and diagnostics carry only
counts and fixed reason/claim tokens (never an application id, title, TryExec
path or URL).

``MAX_REFRESH_EVENTS`` is an *epoch* bound, not a process-lifetime budget. At
an epoch boundary the next trusted event performs the same one bounded producer
call and reconciles the bridge with the current authoritative catalog, then
starts a new epoch. Nothing is deferred to a timer, poll, queue or daemon, and
a rate-limited host signal is never permanently lost: the producer always reads
the latest source state, so the newest catalog wins.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from canopy_core.event_trust import (
    EventTrustBoundary,
    EventTrustError,
    IngressEvent,
    SourceGrant,
)
from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
)
from canopy_features.apps.launch_argv import DESKTOP_ID
from canopy_features.catalog.missing_app_availability import (
    MAX_TRACKED_APPS,
    MissingAppError,
    MissingAppTracker,
)
from canopy_features.launcher.launcher_catalog_ingest import (
    CatalogRow,
    LauncherCatalogSnapshot,
)
from canopy_features.launcher.native_catalog_producer import (
    MAX_SNAPSHOT_BYTES,
    NativeCatalogError,
    produce_catalog_bytes,
)

REFRESH_TOPIC = "app.catalog.changed"
if PROTOCOL_VERSION != 2 or REFRESH_TOPIC not in HOST_EVENT_TOPICS:
    raise RuntimeError("host event contract changed; refresh bridge must be reviewed")

OUTCOME_OK = "refreshed"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_REFUSED = "snapshot_refused"
OUTCOME_REJECTED = "event_rejected"
FIXED_OUTCOMES = (OUTCOME_OK, OUTCOME_REFUSED,
                  OUTCOME_REJECTED, OUTCOME_UNCHANGED)

CLAIM_BOUNDED_REFRESH = "bounded_refresh"
CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"
CLAIM_NO_TIMER = "no_timer_or_poll"
CLAIM_NO_VALUE_ECHO = "no_value_echo"
FIXED_CLAIMS = (CLAIM_BOUNDED_REFRESH, CLAIM_NO_PROCESS_LAUNCH,
                CLAIM_NO_TIMER, CLAIM_NO_VALUE_ECHO)

MAX_REFRESH_EVENTS = 64
MAX_REPORT_HISTORY = 16

__all__ = [
    "CLAIM_BOUNDED_REFRESH",
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_TIMER",
    "CLAIM_NO_VALUE_ECHO",
    "FIXED_CLAIMS",
    "FIXED_OUTCOMES",
    "MAX_REFRESH_EVENTS",
    "MAX_REPORT_HISTORY",
    "OUTCOME_OK",
    "OUTCOME_REFUSED",
    "OUTCOME_REJECTED",
    "OUTCOME_UNCHANGED",
    "REFRESH_TOPIC",
    "CatalogRefreshError",
    "NativeCatalogRefreshBridge",
    "RefreshReport",
]


class CatalogRefreshError(ValueError):
    """An invalid caller, bound, event producer or fact source was supplied."""


def _check_bound(value, maximum, label):
    if type(value) is not int or not 1 <= value <= maximum:
        raise CatalogRefreshError("invalid %s bound" % label)
    return value


@dataclass(frozen=True)
class RefreshReport:
    """One bounded refresh decision; counts and fixed tokens only."""

    outcome: str
    sequence: int
    producer_calls: int
    installed_count: int
    removed_count: int
    snapshot_bytes: int
    claims: tuple = field(default=FIXED_CLAIMS)

    def __post_init__(self):
        if self.outcome not in FIXED_OUTCOMES:
            raise CatalogRefreshError("invalid refresh outcome")
        for name in ("sequence", "producer_calls", "installed_count",
                     "removed_count", "snapshot_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise CatalogRefreshError("invalid %s" % name)
        if self.claims != FIXED_CLAIMS:
            raise CatalogRefreshError("invalid refresh claims")

    def to_dict(self):
        return {
            "outcome": self.outcome,
            "sequence": self.sequence,
            "producer_calls": self.producer_calls,
            "installed_count": self.installed_count,
            "removed_count": self.removed_count,
            "snapshot_bytes": self.snapshot_bytes,
            "claims": list(self.claims),
        }


class NativeCatalogRefreshBridge:
    """Event-driven, bounded refresh from one host topic into the tracker.

    ``source`` is an exact identity granted by trusted host code; only that
    identity may ingest ``app.catalog.changed`` events. ``fact_source`` is an
    optional trusted callable returning real ``tryexec_ok`` and
    ``entry_readable`` booleans for an application id. When it is absent or
    fails, facts are unknown and the observation denies launch permission.
    """

    def __init__(self, applications_dir, tracker, *, source,
                 producer=None, fact_source=None, max_events=MAX_REFRESH_EVENTS):
        if source is None:
            raise CatalogRefreshError("a host source identity is required")
        if not isinstance(tracker, MissingAppTracker):
            raise CatalogRefreshError("a missing-app tracker is required")
        if producer is None:
            producer = produce_catalog_bytes
        if not callable(producer):
            raise CatalogRefreshError("catalog producer must be callable")
        if fact_source is not None and not callable(fact_source):
            raise CatalogRefreshError("fact source must be callable or None")
        self._max_events = _check_bound(max_events, MAX_REFRESH_EVENTS, "refresh event")
        self._applications_dir = applications_dir
        self._tracker = tracker
        self._producer = producer
        self._fact_source = fact_source
        self._source = source
        self._trust = EventTrustBoundary(
            (SourceGrant(source, frozenset({REFRESH_TOPIC})),))
        self._wire = None
        self._ids = frozenset()
        self._catalog = None
        self._last_sequence = 0
        self._events_applied = 0
        self._epoch_events = 0
        self._reconciliations = 0
        self._producer_calls = 0
        self._rejection_count = 0
        self._last_rejection = None
        self._reports = deque(maxlen=MAX_REPORT_HISTORY)
        # One identity-stable callback trusted host code may register on its
        # HostEvents bus for app.catalog.changed.
        self._callback = self._on_event

    @property
    def source(self):
        return self._source

    @property
    def callback(self):
        return self._callback

    @property
    def boundary(self):
        return self._trust

    @property
    def event_count(self):
        return self._events_applied

    @property
    def epoch_events(self):
        """Accepted events in the current bounded epoch (0..max_events)."""
        return self._epoch_events

    @property
    def reconciliations(self):
        """Count of event-driven epoch reconciliations already performed."""
        return self._reconciliations

    @property
    def producer_calls(self):
        return self._producer_calls

    @property
    def rejection_count(self):
        return self._rejection_count

    @property
    def last_rejection(self):
        return self._last_rejection

    def connected(self):
        """True while the trust gate is open; the epoch bound never closes it."""
        return not self._trust.closed

    def close(self):
        self._trust.close()

    def snapshot(self):
        """Last accepted wire bytes, or ``None`` when none was accepted."""
        return self._wire

    def catalog(self):
        """Immutable launcher snapshot projected from the last accepted wire."""
        if self._catalog is None:
            return LauncherCatalogSnapshot(())
        return self._catalog

    def state(self, app_id):
        return self._tracker.state(app_id)

    def reports(self):
        return tuple(self._reports)

    def _advance_epoch(self, reconciling):
        """Keep the epoch counter in 0..max_events without any deferred work."""
        if reconciling:
            self._epoch_events = 1
            self._reconciliations += 1
        else:
            self._epoch_events += 1

    def _note_rejection(self, reason, sequence=0):
        self._rejection_count += 1
        self._last_rejection = reason
        return RefreshReport(OUTCOME_REJECTED, sequence, 0, 0, 0,
                             len(self._wire) if self._wire is not None else 0)

    def _on_event(self, event):
        """Trusted bus callback; records the decision, never raises to host."""
        return self.apply(event)

    def ingest(self, source, topic, payload, **producer_kwargs):
        """Validate one host ingress event and apply exactly one refresh."""
        try:
            self._trust.ingest(source, topic, payload)
        except EventTrustError:
            self._note_rejection(self._trust.last_rejection)
            raise
        batch = self._trust.drain(1)
        return self._process(batch[0], producer_kwargs)

    def apply(self, event, **producer_kwargs):
        """Apply one real ``HostEvent``/``IngressEvent`` from trusted code."""
        sequence = getattr(event, "sequence", 0)
        if type(sequence) is not int or sequence < 1:
            return self._note_rejection("INVALID_EVENT")
        if not isinstance(event, (HostEvent, IngressEvent)):
            return self._note_rejection("INVALID_EVENT", sequence)
        if event.version != PROTOCOL_VERSION:
            return self._note_rejection("INVALID_EVENT", sequence)
        if event.topic != REFRESH_TOPIC:
            return self._note_rejection("UNSUPPORTED_TOPIC", sequence)
        return self._process(event, producer_kwargs)

    def _facts_for(self, app_id):
        """Positive facts only when a trusted source really supplies them."""
        unknown = {"tryexec_ok": False, "entry_readable": False}
        if self._fact_source is None:
            return unknown
        try:
            raw = self._fact_source(app_id)
        except Exception:
            return unknown
        if not isinstance(raw, Mapping):
            return unknown
        tryexec_ok = raw.get("tryexec_ok", False)
        entry_readable = raw.get("entry_readable", False)
        if type(tryexec_ok) is not bool or type(entry_readable) is not bool:
            return unknown
        return {"tryexec_ok": tryexec_ok, "entry_readable": entry_readable}

    def _refusal(self, sequence, reconciling, producer_calls=1):
        self._last_rejection = "SNAPSHOT_REFUSED"
        self._last_sequence = sequence
        self._events_applied += 1
        self._advance_epoch(reconciling)
        report = RefreshReport(
            OUTCOME_REFUSED, sequence, producer_calls, 0, 0,
            len(self._wire) if self._wire is not None else 0)
        self._reports.append(report)
        return report

    @staticmethod
    def _wire_ids(wire):
        ids = []
        for line in wire.decode("utf-8", "strict").splitlines():
            app_id, separator, _title = line.partition("\t")
            if not separator or DESKTOP_ID.fullmatch(app_id) is None:
                raise NativeCatalogError("catalog wire refused")
            if app_id in ids:
                raise NativeCatalogError("catalog wire refused")
            ids.append(app_id)
        return frozenset(ids)

    @staticmethod
    def _project_catalog(wire):
        rows = []
        for line in wire.decode("utf-8", "strict").splitlines():
            app_id, separator, title = line.partition("\t")
            if not separator:
                raise NativeCatalogError("catalog wire refused")
            rows.append(CatalogRow(app_id, title, ()))
        return LauncherCatalogSnapshot(tuple(rows), raw_count=len(rows))

    def _process(self, event, producer_kwargs):
        sequence = event.sequence
        if self._trust.closed:
            # Direct apply() after close must fail closed like ingest().
            return self._note_rejection("CLOSED", sequence)
        if sequence <= self._last_sequence:
            return self._note_rejection("REPLAYED_SEQUENCE", sequence)
        # An epoch boundary is a normal event-driven reconciliation: the one
        # bounded producer call below re-reads the authoritative source, so
        # the newest catalog always wins and no signal is deferred or lost.
        reconciling = self._epoch_events >= self._max_events

        self._producer_calls += 1
        try:
            wire = self._producer(self._applications_dir, **producer_kwargs)
            if type(wire) is not bytes or len(wire) > MAX_SNAPSHOT_BYTES:
                raise NativeCatalogError("catalog snapshot refused")
            ids = self._wire_ids(wire)
            catalog = self._project_catalog(wire)
        except (NativeCatalogError, MissingAppError, OSError, TypeError,
                ValueError, UnicodeError):
            # Atomic refusal: no wire, catalog or availability state is
            # committed, and no source text is echoed into the report.
            return self._refusal(sequence, reconciling, 1)

        installed = ids - self._ids
        removed = self._ids - ids
        tracked = len(self._tracker.snapshot()) + len(installed)
        if tracked > MAX_TRACKED_APPS:
            return self._refusal(sequence, reconciling, 1)

        try:
            for app_id in sorted(installed):
                self._tracker.observe(
                    app_id, in_catalog=True, **self._facts_for(app_id))
            for app_id in sorted(removed):
                # Absence is an authoritative negative: no TryExec or read
                # positive fact may be inferred from a stale catalog row.
                self._tracker.observe(
                    app_id, in_catalog=False,
                    tryexec_ok=False, entry_readable=False)
        except Exception:
            return self._refusal(sequence, reconciling, 1)

        self._wire = wire
        self._ids = ids
        self._catalog = catalog
        self._last_sequence = sequence
        self._events_applied += 1
        self._advance_epoch(reconciling)
        outcome = OUTCOME_OK if installed or removed else OUTCOME_UNCHANGED
        report = RefreshReport(outcome, sequence, 1, len(installed),
                               len(removed), len(wire))
        self._reports.append(report)
        return report
