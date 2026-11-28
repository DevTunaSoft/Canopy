"""Bounded read-only Plasma/KWin/logind recovery integration.

This class composes the already-merged host-boundary adapter
``canopy_features.reliability.suspend_resume_native.SuspendResumeNativePath``
with the new immutable recovery records in
``canopy_features.session_recovery.contracts``. It adds no daemon, bus client,
socket, subprocess, poll loop, timer, thread or I/O. It never suspends or
resumes the host and never executes the fallback it declares.

A trusted caller supplies already-collected facts; every observation is
bounded and every conclusion fails closed.
"""
from __future__ import annotations

from collections import deque
from types import MappingProxyType

from canopy_core.host_events import HostEvent
from canopy_features.reliability.lock_session_events import SessionState
from canopy_features.reliability.suspend_resume_native import (
    SuspendResumeNativePath)
from canopy_features.session_recovery.contracts import (
    DESKTOP_REOBSERVED, FALLBACK, FALLBACK_READY, MAX_CHECKPOINTS, MISSING,
    NOT_RUN, OBSERVED, POST_CAPTURED, PRE_CAPTURED,
    RESUME_CONFIRMED, SESSION_PRESERVED, STATIC_SOURCE_ONLY,
    SUSPEND_CONFIRMED, WORK_PRESERVED, Checkpoint,
    Fallback, Preservation, RecoverySnapshot, SessionRecoveryError,
    StateCapture)

__all__ = ["PlasmaRecoveryIntegration"]


def _state(flag):
    """Map a durable boolean to a checkpoint state without guessing."""
    if flag is True:
        return OBSERVED
    if flag is False:
        return MISSING
    return NOT_RUN


class PlasmaRecoveryIntegration:
    """Compose existing fail-closed decisions with recovery checkpoints."""

    def __init__(self):
        self._path = SuspendResumeNativePath()
        self._checkpoints = deque(maxlen=MAX_CHECKPOINTS)
        self._captures = {}
        self._suspend = None
        self._resume = None
        self._preservation = None
        self._reobserved = None
        self._fallback = None
        self._closed = False

    def _mutable(self):
        if self._closed:
            raise SessionRecoveryError("recovery integration is closed")

    def _append(self, name, state, label=STATIC_SOURCE_ONLY):
        self._checkpoints.append(Checkpoint(name, state, label))

    # -- existing host boundary, reused unchanged ------------------------
    def observe_event(self, event):
        """Fold one already-delivered HostEvent through the existing path."""
        self._mutable()
        if type(event) is not HostEvent:
            raise SessionRecoveryError("observation requires a HostEvent")
        self._path.submit(event)
        return self._path.drain()

    def observe_session_state(self, state):
        """Fold an existing reconciled SessionState through the same path."""
        self._mutable()
        if type(state) is not SessionState:
            raise SessionRecoveryError("session observation requires SessionState")
        return self._path.observe_session_state(state)

    def availability(self):
        """Read-only availability decision; never an action or execution."""
        return self._path.decide("read_status")

    # -- checkpoints -----------------------------------------------------
    def capture(self, stage, *, source, interface, facts):
        """Record a pre/post desktop state capture supplied by the host."""
        self._mutable()
        if stage not in ("pre", "post"):
            raise SessionRecoveryError("capture stage must be pre or post")
        record = StateCapture(stage, source, interface, facts)
        self._captures[stage] = record
        name = PRE_CAPTURED if stage == "pre" else POST_CAPTURED
        self._append(name, OBSERVED if record.complete else NOT_RUN)
        return record

    def mark_suspend(self, observed, *, evidence_label=STATIC_SOURCE_ONLY):
        """Record an already-observed suspend; performs no suspend request."""
        self._mutable()
        if type(observed) is not bool:
            raise SessionRecoveryError("suspend observation must be boolean")
        self._suspend = Checkpoint(SUSPEND_CONFIRMED, _state(observed), evidence_label)
        self._append(SUSPEND_CONFIRMED, _state(observed), evidence_label)
        return self._suspend

    def mark_resume(self, observed, *, evidence_label=STATIC_SOURCE_ONLY):
        """Record an already-observed resume; performs no resume request."""
        self._mutable()
        if type(observed) is not bool:
            raise SessionRecoveryError("resume observation must be boolean")
        self._resume = Checkpoint(RESUME_CONFIRMED, _state(observed), evidence_label)
        self._append(RESUME_CONFIRMED, _state(observed), evidence_label)
        return self._resume

    def preserve(self, *, session_id_stable, work_area_stable,
                 windows_restored, source):
        """Record preservation of the session and the user's work."""
        self._mutable()
        record = Preservation(session_id_stable, work_area_stable,
                              windows_restored, source)
        self._preservation = record
        self._append(SESSION_PRESERVED, _state(record.session_id_stable))
        work_ok = (record.work_area_stable is True
                   and record.windows_restored is True)
        work_state = (OBSERVED if work_ok else
                      NOT_RUN if record.work_area_stable is None
                      or record.windows_restored is None else MISSING)
        self._append(WORK_PRESERVED, work_state)
        return record

    def reobserve(self, confirmed):
        """Acknowledge a re-observed desktop after resume; never automatic."""
        self._mutable()
        if type(confirmed) is not bool:
            raise SessionRecoveryError("re-observation must be boolean")
        self._reobserved = confirmed
        self._append(DESKTOP_REOBSERVED, _state(confirmed))
        return confirmed

    def fallback(self, reason):
        """Declare safe stock-Plasma fallback; no action is performed."""
        self._mutable()
        record = Fallback(reason)
        self._fallback = record
        self._append(FALLBACK_READY, FALLBACK)
        return record

    # -- conclusion ------------------------------------------------------
    def snapshot(self, *, evidence_label=STATIC_SOURCE_ONLY):
        """Immutable recovery snapshot with a fail-closed verdict."""
        self._mutable()
        if type(evidence_label) is not str:
            raise SessionRecoveryError("invalid evidence label")
        label = evidence_label
        if self._path.decide("read_status").available is not True:
            # An untrusted host boundary can never support a native PASS.
            if self._fallback is None:
                self.fallback("host-unavailable")
            label = STATIC_SOURCE_ONLY
        return RecoverySnapshot(
            evidence_label=label,
            pre=self._captures.get("pre"),
            post=self._captures.get("post"),
            suspend=self._suspend,
            resume=self._resume,
            preservation=self._preservation,
            reobserved=self._reobserved,
            checkpoints=tuple(self._checkpoints),
            fallback=self._fallback,
        )

    def close(self):
        """Irreversible read-only cleanup; declares fallback, executes none."""
        if self._closed:
            return
        if self._fallback is None:
            self._fallback = Fallback("path-closed")
            self._append(FALLBACK_READY, FALLBACK)
        self._path.close()
        self._closed = True

    def view(self):
        return MappingProxyType({
            "closed": self._closed,
            "boundary": self._path.view()["boundary"],
            "availability": self.availability().to_dict(),
            "captures": tuple(sorted(self._captures)),
            "checkpoints": tuple(item.to_dict() for item in self._checkpoints),
            "reobserved": self._reobserved,
            "fallback": self._fallback.to_dict() if self._fallback is not None else None,
        })
