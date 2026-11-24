"""Pure, bounded launch-outcome and retry reconciliation for a host.

The host supplies previously issued launch events and the immutable preview
record that authorised the launch. This module returns one deterministic,
fail-closed decision about whether the launch succeeded, should be retried, or
has exhausted its retry budget. It never launches a process, opens a file,
polls, retains state or touches a desktop.

The snapshot carries counts and fixed negative claims only. No application id,
failure reason, PID or other source text is copied into it or its ``to_dict``
bridge, so untrusted strings cannot reach a log or a host bridge.
"""
from dataclasses import dataclass
from typing import Tuple

from canopy_features.apps.app_launch_preview import (
    STATUS_READY as PREVIEW_READY,
    AppLaunchPreview,
)
from canopy_features.apps.launch_argv import DESKTOP_ID

MAX_EVENTS = 256
MAX_RETRIES = 2
MAX_SEQUENCE = 2 ** 31 - 1
MAX_PID = 2 ** 31 - 1

STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_RETRY = "RETRY"
STATUS_GIVE_UP = "GIVE_UP"
STATUS_IDLE = "IDLE"

REASON_OK = "ok"
REASON_NO_EVENTS = "no_events"
REASON_RETRY_BUDGET = "retry_budget"
REASON_RETRY_EXHAUSTED = "retry_exhausted"

_FAILURE_REASONS = frozenset((
    "target-missing", "spawn-refused", "launch-denied",
))

CLAIM_NO_APP_ID_ECHO = "no_app_id_echo"
CLAIM_NO_REASON_TEXT_ECHO = "no_reason_text_echo"
CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"
CLAIM_NO_IO = "no_io"
CLAIM_NO_GEOMETRY_READ = "no_geometry_read"
CLAIM_NO_VISUAL_CHANGE = "no_visual_change"

FIXED_CLAIMS = (
    CLAIM_NO_APP_ID_ECHO,
    CLAIM_NO_GEOMETRY_READ,
    CLAIM_NO_IO,
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_REASON_TEXT_ECHO,
    CLAIM_NO_VISUAL_CHANGE,
)

__all__ = [
    "CLAIM_NO_APP_ID_ECHO",
    "CLAIM_NO_GEOMETRY_READ",
    "CLAIM_NO_IO",
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_REASON_TEXT_ECHO",
    "CLAIM_NO_VISUAL_CHANGE",
    "FIXED_CLAIMS",
    "MAX_EVENTS",
    "MAX_PID",
    "MAX_RETRIES",
    "MAX_SEQUENCE",
    "REASON_NO_EVENTS",
    "REASON_OK",
    "REASON_RETRY_BUDGET",
    "REASON_RETRY_EXHAUSTED",
    "STATUS_GIVE_UP",
    "STATUS_IDLE",
    "STATUS_RETRY",
    "STATUS_SUCCEEDED",
    "LaunchExited",
    "LaunchFailed",
    "LaunchSucceeded",
    "LaunchOutcomeSnapshot",
    "OutcomeInputError",
    "compose_launch_outcome",
]


class OutcomeInputError(ValueError):
    """Malformed caller input: wrong record type, bad field or bound breach."""


@dataclass(frozen=True)
class LaunchSucceeded:
    sequence: int
    app_id: str
    pid: int


@dataclass(frozen=True)
class LaunchFailed:
    sequence: int
    app_id: str
    reason: str


@dataclass(frozen=True)
class LaunchExited:
    sequence: int
    app_id: str
    code: int


@dataclass(frozen=True)
class LaunchOutcomeSnapshot:
    """One bounded host decision; counts and claims only."""

    status: str
    reason: str
    event_count: int = 0
    relevant_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    claims: Tuple[str, ...] = ()

    def to_dict(self):
        """Plain bounded diagnostics mapping; no source text is echoed."""
        return {
            "status": self.status,
            "reason": self.reason,
            "event_count": self.event_count,
            "relevant_count": self.relevant_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "retry_count": self.retry_count,
            "claims": list(self.claims),
        }


def _check_sequence(value):
    if type(value) is not int or not 0 <= value <= MAX_SEQUENCE:
        raise OutcomeInputError("invalid event sequence")


def _check_event(event):
    if isinstance(event, LaunchSucceeded):
        _check_sequence(event.sequence)
        if type(event.pid) is not int or not 1 <= event.pid <= MAX_PID:
            raise OutcomeInputError("invalid launch pid")
    elif isinstance(event, LaunchFailed):
        _check_sequence(event.sequence)
        if type(event.reason) is not str or event.reason not in _FAILURE_REASONS:
            raise OutcomeInputError("unrecognised launch failure reason")
    elif isinstance(event, LaunchExited):
        _check_sequence(event.sequence)
        if type(event.code) is not int or isinstance(event.code, bool):
            raise OutcomeInputError("invalid exit code")
    else:
        raise OutcomeInputError("unsupported launch outcome event")


def compose_launch_outcome(
    app_id, preview, events, *, max_events=MAX_EVENTS, max_retries=MAX_RETRIES,
):
    """Reconcile bounded outcome events into one no-echo host decision.

    Events naming another application are counted but never applied. A success
    is terminal; otherwise failures within the retry budget yield RETRY and a
    larger count yields GIVE_UP. One event sequence may only carry one outcome
    class: a success and a failure sharing an id are contradictory caller
    input and fail closed rather than producing a false launch-success claim.
    All inputs are validated before any decision.
    """
    if type(app_id) is not str or DESKTOP_ID.fullmatch(app_id) is None:
        raise OutcomeInputError("invalid desktop application id")
    # Gate on the exact status label type before comparing it. A hostile str
    # subclass could otherwise fake READY (claiming a false launch success on
    # a denied preview) or leak a raw exception from an overridden __ne__.
    if (not isinstance(preview, AppLaunchPreview)
            or type(preview.status) is not str
            or preview.status != PREVIEW_READY):
        raise OutcomeInputError("expected a ready AppLaunchPreview")
    if type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS:
        raise OutcomeInputError("invalid event bound")
    if type(max_retries) is not int or not 0 <= max_retries <= MAX_RETRIES:
        raise OutcomeInputError("invalid retry bound")
    if isinstance(events, (str, bytes, bytearray, dict)) or not hasattr(events, "__iter__"):
        raise OutcomeInputError("events must be an iterable")

    event_count = 0
    relevant = 0
    succeeded = 0
    failures = 0
    success_ids = set()
    failure_ids = set()
    for event in events:
        event_count += 1
        if event_count > max_events:
            raise OutcomeInputError("too many launch outcome events")
        _check_event(event)
        if type(event.app_id) is not str or event.app_id != app_id:
            if type(event.app_id) is not str:
                raise OutcomeInputError("invalid event application id")
            continue
        relevant += 1
        if isinstance(event, LaunchSucceeded):
            succeeded += 1
            is_success = True
        elif isinstance(event, LaunchFailed):
            failures += 1
            is_success = False
        elif event.code == 0:
            succeeded += 1
            is_success = True
        else:
            failures += 1
            is_success = False
        if is_success:
            if event.sequence in failure_ids:
                raise OutcomeInputError("contradictory launch outcome event id")
            success_ids.add(event.sequence)
        else:
            if event.sequence in success_ids:
                raise OutcomeInputError("contradictory launch outcome event id")
            failure_ids.add(event.sequence)

    if relevant == 0:
        return LaunchOutcomeSnapshot(STATUS_IDLE, REASON_NO_EVENTS,
                                     event_count=event_count, claims=FIXED_CLAIMS)
    if succeeded:
        return LaunchOutcomeSnapshot(
            STATUS_SUCCEEDED, REASON_OK, event_count=event_count,
            relevant_count=relevant, success_count=succeeded,
            failure_count=failures, claims=FIXED_CLAIMS)
    retries = min(failures, max_retries)
    status = STATUS_RETRY if failures <= max_retries else STATUS_GIVE_UP
    reason = REASON_RETRY_BUDGET if status == STATUS_RETRY else REASON_RETRY_EXHAUSTED
    return LaunchOutcomeSnapshot(
        status, reason, event_count=event_count, relevant_count=relevant,
        success_count=0, failure_count=failures, retry_count=retries,
        claims=FIXED_CLAIMS,
    )
