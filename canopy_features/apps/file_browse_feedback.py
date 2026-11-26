"""Fixed, path-free failure feedback for file/folder browsing.

Pure and offline: this module reads no filesystem, launches no process, uses
no network, keeps no state and touches no QML, artwork or protected source. A
trusted host supplies one failure reason code; this module returns an
immutable record with fixed user-facing text plus a payload for the *existing*
host event bus.

Reason codes and their message vocabulary are mirrored verbatim from
``canopy_features.apps.native_file_open`` (PE-016, open PR #666). That module
is not present at this base tip, so it is deliberately not imported: the
contract is self-contained and cannot silently drift with an unmerged branch.

Transport reuses the existing v2 ``canopy_core.host_events`` topic
``window.state.changed`` and its existing ``state`` field. No topic, payload
field, protocol version or contract documentation is extended here.
"""
from dataclasses import dataclass
from typing import Tuple

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
)

APPROVED = "APPROVED"
DENIED = "DENIED"

# Fixed reason vocabulary from native_file_open: validation refusals first,
# then host-side open failures. "permission_denied" and the malformed-path
# codes are the two failure classes this module exposes to a browser.
REASON_OK = "ok"
REASON_HOME_UNAVAILABLE = "home_unavailable"
REASON_INVALID_PATH = "invalid_path"
REASON_EMPTY_PATH = "empty_path"
REASON_TOO_LONG = "too_long"
REASON_MISSING_TARGET = "missing_target"
REASON_UNSUPPORTED_TYPE = "unsupported_type"
REASON_OUTSIDE_HOME = "outside_home"
REASON_HANDLER_UNAVAILABLE = "handler_unavailable"
REASON_PERMISSION_DENIED = "permission_denied"
REASON_HANDLER_MISSING = "handler_missing"
REASON_NO_DEFAULT_APP = "no_default_app"
REASON_OPEN_FAILED = "open_failed"
REASON_CANCELLED = "cancelled"
REASON_UNKNOWN = "unknown"

# Existing v2 topic and field, reused verbatim. Fail closed at import if the
# host contract ever changes underneath this adapter.
FEEDBACK_TOPIC = "window.state.changed"
FEEDBACK_FIELD = "state"
if PROTOCOL_VERSION != 2 or FEEDBACK_TOPIC not in HOST_EVENT_TOPICS:
    raise RuntimeError("host event contract changed; feedback adapter must be reviewed")  # pragma: no cover

# Exactly the native_file_open fixed messages; no caller text is ever echoed.
FEEDBACK = {
    REASON_HOME_UNAVAILABLE: "Your home folder is unavailable; nothing was opened.",
    REASON_INVALID_PATH: "That item has an invalid path; nothing was opened.",
    REASON_EMPTY_PATH: "No file or folder was selected; nothing was opened.",
    REASON_TOO_LONG: "That item's path is too long; nothing was opened.",
    REASON_MISSING_TARGET: "That file or folder no longer exists; nothing was opened.",
    REASON_UNSUPPORTED_TYPE: "Only files and folders can be opened; nothing was opened.",
    REASON_OUTSIDE_HOME: "Only items in your home folder can be opened here.",
    REASON_HANDLER_UNAVAILABLE: "No supported default-app handler is available.",
    REASON_PERMISSION_DENIED: "Permission was denied; nothing was opened.",
    REASON_HANDLER_MISSING: "The default application handler is not installed.",
    REASON_NO_DEFAULT_APP: "No default application is configured for this item.",
    REASON_OPEN_FAILED: "The system could not open this item.",
    REASON_CANCELLED: "Opening this item was cancelled.",
    REASON_UNKNOWN: "The item could not be opened for an unknown reason.",
}

_INVALID_REPORT_FEEDBACK = "The open failure report was not valid."
_UNRECOGNIZED_FEEDBACK = "The system reported an unrecognized open failure."

CLAIM_NO_PATH_ECHO = "no_path_echo"
CLAIM_NO_IO = "no_io"
CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"
CLAIM_NO_VISUAL_CHANGE = "no_visual_change"
FIXED_CLAIMS: Tuple[str, ...] = (
    CLAIM_NO_IO,
    CLAIM_NO_PATH_ECHO,
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_VISUAL_CHANGE,
)

__all__ = [
    "APPROVED",
    "CLAIM_NO_IO",
    "CLAIM_NO_PATH_ECHO",
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_VISUAL_CHANGE",
    "DENIED",
    "FEEDBACK",
    "FEEDBACK_FIELD",
    "FEEDBACK_TOPIC",
    "FIXED_CLAIMS",
    "REASON_CANCELLED",
    "REASON_EMPTY_PATH",
    "REASON_HANDLER_MISSING",
    "REASON_HANDLER_UNAVAILABLE",
    "REASON_HOME_UNAVAILABLE",
    "REASON_INVALID_PATH",
    "REASON_MISSING_TARGET",
    "REASON_NO_DEFAULT_APP",
    "REASON_OK",
    "REASON_OPEN_FAILED",
    "REASON_OUTSIDE_HOME",
    "REASON_PERMISSION_DENIED",
    "REASON_TOO_LONG",
    "REASON_UNKNOWN",
    "REASON_UNSUPPORTED_TYPE",
    "BrowseFeedback",
    "BrowseFeedbackError",
    "browse_failure",
    "failure_event_payload",
    "failure_feedback",
    "from_host_event",
]


class BrowseFeedbackError(ValueError):
    """Malformed, unbounded or untrusted browse failure input."""


def failure_feedback(reason: object) -> str:
    """Fixed text for one reason code, never echoing caller-supplied text.

    An exact ``str`` is required: a subclass can override equality and turn a
    hostile value into an approved message. Wrong types and unknown codes get
    their own fixed messages, so an untrusted path cannot become status text.
    """
    if type(reason) is not str:
        return _INVALID_REPORT_FEEDBACK
    message = FEEDBACK.get(reason)
    return message if message is not None else _UNRECOGNIZED_FEEDBACK


@dataclass(frozen=True, slots=True)
class BrowseFeedback:
    """Immutable host-facing feedback record; no path or target is carried."""

    status: str
    reason: str
    feedback: str
    claims: Tuple[str, ...] = FIXED_CLAIMS

    def __post_init__(self):
        if (type(self.status) is not str or type(self.reason) is not str
                or type(self.feedback) is not str):
            raise BrowseFeedbackError("bad feedback field type")
        if type(self.claims) is not tuple or self.claims != FIXED_CLAIMS:
            raise BrowseFeedbackError("feedback claims must be the fixed set")
        if self.feedback != failure_feedback(self.reason):
            raise BrowseFeedbackError("feedback text does not match its reason")

    @property
    def approved(self):
        return self.status == APPROVED

    def to_dict(self):
        """Fresh plain mapping; never carries a path, URI or raw caller text."""
        return {
            "status": self.status,
            "reason": self.reason,
            "feedback": self.feedback,
            "claims": list(self.claims),
        }


def browse_failure(reason: object) -> BrowseFeedback:
    """Build one DENIED record for a known failure code; success is not one."""
    if type(reason) is not str or reason not in FEEDBACK:
        raise BrowseFeedbackError("unrecognized browse failure reason")
    return BrowseFeedback(DENIED, reason, FEEDBACK[reason], FIXED_CLAIMS)


def failure_event_payload(reason: object) -> dict:
    """Payload for the existing host topic, using only its existing field."""
    record = browse_failure(reason)
    return {FEEDBACK_FIELD: record.reason}


def from_host_event(event: object) -> BrowseFeedback:
    """Project one real delivered host event into bounded failure feedback.

    Only genuine ``HostEvent`` objects on the existing feedback topic with the
    current protocol version are read. A missing or unrecognized state value
    fails closed as ``unknown``; no payload value is ever echoed into feedback.
    """
    if type(event) is not HostEvent:
        raise BrowseFeedbackError("expected a real HostEvent")
    if (event.version != PROTOCOL_VERSION or type(event.topic) is not str
            or event.topic != FEEDBACK_TOPIC):
        raise BrowseFeedbackError("unsupported feedback host event envelope")
    payload = event.payload
    reason = payload.get(FEEDBACK_FIELD)
    if type(reason) is not str or reason not in FEEDBACK:
        return browse_failure(REASON_UNKNOWN)
    return browse_failure(reason)
