"""Pure, bounded classifier for observed native app-launch outcomes.

This module does not start processes, read the desktop database, open sockets,
poll, or observe a real Qt/Linux-Mint session. It classifies one outcome that a
trusted host adapter already observed and reports a small, safe contract.

"Never invent success" is the core rule: a timeout, missing data, a generic
failure, or contradictory evidence can never produce ``SUCCESS``. Only an
explicit positive confirmation (GIO's ``g_app_info_launch`` returned TRUE,
surfaced as ``STATUS_REQUESTED`` with no error) yields ``SUCCESS``.

Future integration still needed: a trusted adapter in the compiled Qt
application must pass real GIO results into this module. This component alone
does not prove a working desktop, a launch, or a window appearing.
"""
from dataclasses import dataclass
from typing import Optional

PROTOCOL_VERSION = 1

# Raw statuses a trusted launcher adapter may report. STATUS_REQUESTED is the
# only positive signal; it maps to the existing compiled GIO TRUE return.
STATUS_REQUESTED = "requested"
STATUS_FAILED = "failed"
STATUS_UNAVAILABLE = "unavailable"
STATUS_REJECTED = "rejected"
STATUS_DISABLED = "disabled"
STATUS_DENIED = "denied"
STATUS_TIMED_OUT = "timed_out"
STATUS_UNKNOWN = "unknown"
STATUSES = frozenset({
    STATUS_REQUESTED, STATUS_FAILED, STATUS_UNAVAILABLE, STATUS_REJECTED,
    STATUS_DISABLED, STATUS_DENIED, STATUS_TIMED_OUT, STATUS_UNKNOWN,
})

# GLib/GIO error-code tokens understood at this boundary. Unknown codes are
# never echoed and never mapped to success.
ERROR_PERMISSION_DENIED = "PERMISSION_DENIED"
ERROR_ACCESS_DENIED = "ACCESS_DENIED"
ERROR_NOT_AUTHORIZED = "NOT_AUTHORIZED"
ERROR_TIMED_OUT = "TIMED_OUT"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_NOT_SUPPORTED = "NOT_SUPPORTED"

# Result categories and their stable, secret-free UI message keys.
CATEGORY_SUCCESS = "success"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_DENIED = "denied"
CATEGORY_MISSING_APP = "missing_app"
CATEGORY_DISABLED = "disabled"
CATEGORY_INVALID_REQUEST = "invalid_request"
CATEGORY_UNSUPPORTED = "unsupported"
CATEGORY_UNKNOWN = "unknown"
CATEGORIES = frozenset({
    CATEGORY_SUCCESS, CATEGORY_TIMEOUT, CATEGORY_DENIED, CATEGORY_MISSING_APP,
    CATEGORY_DISABLED, CATEGORY_INVALID_REQUEST, CATEGORY_UNSUPPORTED,
    CATEGORY_UNKNOWN,
})

MESSAGE_KEYS = {
    CATEGORY_SUCCESS: "launch.succeeded",
    CATEGORY_TIMEOUT: "launch.timed_out",
    CATEGORY_DENIED: "launch.permission_denied",
    CATEGORY_MISSING_APP: "launch.app_missing",
    CATEGORY_DISABLED: "launch.disabled",
    CATEGORY_INVALID_REQUEST: "launch.invalid_request",
    CATEGORY_UNSUPPORTED: "launch.unsupported",
    CATEGORY_UNKNOWN: "launch.unknown",
}

# A category is "actionable" only when the host has a specific, safe next step.
_ACTIONABLE = frozenset({
    CATEGORY_TIMEOUT, CATEGORY_DENIED, CATEGORY_MISSING_APP, CATEGORY_DISABLED,
    CATEGORY_INVALID_REQUEST, CATEGORY_UNSUPPORTED,
})
_RETRYABLE = frozenset({CATEGORY_TIMEOUT})

MAX_TOKEN_BYTES = 64
MAX_DURATION_MS = 86_400_000  # 24 hours; bounds untrusted duration values.

# Existing compiled-launcher log markers (SystemAppLauncher.cpp) mapped to
# statuses. Unrecognised markers map to STATUS_UNKNOWN, never to success.
LOG_MARKER_STATUS = {
    "CANOPY_APP_LAUNCH_REQUESTED": STATUS_REQUESTED,
    "CANOPY_APP_LAUNCH_FAILED": STATUS_FAILED,
    "CANOPY_APP_LAUNCH_UNAVAILABLE": STATUS_UNAVAILABLE,
    "CANOPY_APP_LAUNCH_REJECTED": STATUS_REJECTED,
}


class LaunchContractError(ValueError):
    """Malformed, oversized or untrusted launch outcome input."""


def _token(value, field, *, required=False):
    if value is None:
        if required:
            raise LaunchContractError(field + " is required")
        return None
    if type(value) is not str:
        raise LaunchContractError(field + " must be a string")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeEncodeError as exc:
        raise LaunchContractError(field + " is not valid UTF-8") from exc
    if size > MAX_TOKEN_BYTES:
        raise LaunchContractError(field + " exceeds bound")
    return value


def _duration(value, field):
    if value is None:
        return None
    if type(value) is not int:
        raise LaunchContractError(field + " must be an integer")
    if not 0 <= value <= MAX_DURATION_MS:
        raise LaunchContractError(field + " out of range")
    return value


@dataclass(frozen=True)
class LaunchOutcome:
    """One bounded, already-observed launch attempt from a trusted adapter."""

    status: str
    error_code: Optional[str] = None
    error_domain: Optional[str] = None
    elapsed_ms: Optional[int] = None
    timeout_ms: Optional[int] = None

    def __post_init__(self):
        object.__setattr__(self, "status", _token(self.status, "status", required=True))
        object.__setattr__(self, "error_code", _token(self.error_code, "error_code"))
        object.__setattr__(self, "error_domain", _token(self.error_domain, "error_domain"))
        object.__setattr__(self, "elapsed_ms", _duration(self.elapsed_ms, "elapsed_ms"))
        object.__setattr__(self, "timeout_ms", _duration(self.timeout_ms, "timeout_ms"))


@dataclass(frozen=True)
class LaunchClassification:
    """Safe result of classifying a launch outcome. No raw errors or paths."""

    category: str
    message_key: str
    actionable: bool
    retryable: bool
    confirmed: bool
    version: int = PROTOCOL_VERSION

    @property
    def succeeded(self):
        """True only for explicit, confirmed positive confirmation."""
        return self.category == CATEGORY_SUCCESS


def _result(category, *, confirmed):
    return LaunchClassification(
        category=category,
        message_key=MESSAGE_KEYS[category],
        actionable=category in _ACTIONABLE,
        retryable=category in _RETRYABLE,
        confirmed=confirmed,
    )


def status_from_log_marker(marker):
    """Map an existing compiled-launcher log marker to a status token.

    Unknown markers return STATUS_UNKNOWN. No marker is ever treated as a
    positive confirmation unless it is the explicit REQUESTED marker.
    """
    _token(marker, "marker", required=True)
    return LOG_MARKER_STATUS.get(marker, STATUS_UNKNOWN)


def classify(outcome):
    """Classify one LaunchOutcome. Pure, O(1), no state and no side effects."""
    if type(outcome) is not LaunchOutcome:
        raise LaunchContractError("LaunchOutcome required")

    status = outcome.status
    code = outcome.error_code

    # 1. A bounded wait that expired is never success, even if the raw status
    #    looks positive. Timeout takes precedence over every other signal.
    timed_out = (
        status == STATUS_TIMED_OUT
        or code == ERROR_TIMED_OUT
        or (outcome.elapsed_ms is not None
            and outcome.timeout_ms is not None
            and outcome.elapsed_ms >= outcome.timeout_ms)
    )
    if timed_out:
        return _result(CATEGORY_TIMEOUT, confirmed=True)

    # 2. Permission or policy refusal.
    if status == STATUS_DENIED or code in (
            ERROR_PERMISSION_DENIED, ERROR_ACCESS_DENIED, ERROR_NOT_AUTHORIZED):
        return _result(CATEGORY_DENIED, confirmed=True)

    # 3. No launchable desktop entry was present or found.
    if status == STATUS_UNAVAILABLE or code == ERROR_NOT_FOUND:
        return _result(CATEGORY_MISSING_APP, confirmed=True)

    # 4. Opt-in native launching is off.
    if status == STATUS_DISABLED:
        return _result(CATEGORY_DISABLED, confirmed=True)

    # 5. Unknown dock action or otherwise invalid request.
    if status == STATUS_REJECTED:
        return _result(CATEGORY_INVALID_REQUEST, confirmed=True)

    # 6. Explicitly unsupported launch (for example no registered handler).
    if code == ERROR_NOT_SUPPORTED:
        return _result(CATEGORY_UNSUPPORTED, confirmed=True)

    # 7. Success requires a positive confirmation AND no error signal at all.
    #    Contradictory evidence (requested plus an error) falls through to UNKNOWN.
    if (status == STATUS_REQUESTED and code is None
            and outcome.error_domain is None):
        return _result(CATEGORY_SUCCESS, confirmed=True)

    # 8. Fail closed: generic failure, unknown status, missing data and
    #    contradictions are never reported as success.
    return _result(CATEGORY_UNKNOWN, confirmed=False)
