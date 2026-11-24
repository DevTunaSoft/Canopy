"""Compose an auditable Files-intent preview from already-tested decisions.

Pure data only: no filesystem access, process launch, network, timers or GUI.
The host supplies the immutable outputs of ``form_file_manager_intent`` and
``WorkingDirectoryPolicy.evaluate``; this module reconciles them into one
bounded decision record with stable reason codes. Denials carry no path or
URI so untrusted text cannot leak into logs or a QML bridge.
"""
from dataclasses import dataclass
import os
from typing import Optional

from canopy_features.apps.file_manager_intent import LAUNCH_ACTION, FileManagerIntent
from canopy_features.apps.working_directory_policy import Decision

__all__ = [
    "APPROVED",
    "DENIED",
    "REASON_INVALID_INPUT",
    "REASON_OK",
    "REASON_PATH_MISMATCH",
    "REASON_POLICY_DENIED",
    "REASON_UNSAFE_ACTION",
    "REASON_UNSAFE_URI",
    "FilesIntentPreview",
    "PreviewInputError",
    "compose_files_intent_preview",
]

APPROVED = "APPROVED"
DENIED = "DENIED"

REASON_OK = "ok"
REASON_INVALID_INPUT = "invalid_input"
REASON_POLICY_DENIED = "policy_denied"
REASON_PATH_MISMATCH = "path_mismatch"
REASON_UNSAFE_ACTION = "unsafe_action"
REASON_UNSAFE_URI = "unsafe_uri"

_MAX_FIELD_CHARS = 4096
_SHELL_META = ";&|$`<>(){}"


class PreviewInputError(ValueError):
    """Caller passed objects that are not the two expected source records."""


@dataclass(frozen=True)
class FilesIntentPreview:
    """Immutable host-facing result of reconciling the two source decisions."""

    status: str
    reason: str
    action: Optional[str] = None
    uri: Optional[str] = None
    directory: Optional[str] = None
    intent_reason: Optional[str] = None
    policy_reason: Optional[str] = None

    @property
    def approved(self):
        return self.status == APPROVED

    def to_dict(self):
        """Plain bounded mapping for a trusted host; denials carry no path."""
        return {
            "status": self.status,
            "reason": self.reason,
            "action": self.action,
            "uri": self.uri,
            "directory": self.directory,
            "intent_reason": self.intent_reason,
            "policy_reason": self.policy_reason,
        }


def _text_ok(value):
    """Bounded printable text, free of control characters and null bytes.

    Require an exact ``str``: a str subclass can override iteration,
    containment, ``startswith`` or case/separator folding, so an ``isinstance``
    check would let a hostile record forge a clean safety scan (or raise a raw
    exception mid-scan) while carrying unsafe text into an APPROVED preview.
    """
    return (type(value) is str and 0 < len(value) <= _MAX_FIELD_CHARS
            and all(char >= " " and char != "\x7f" for char in value))


def _uri_ok(uri):
    """Only a bounded file-scheme URI without shell metacharacters."""
    return (_text_ok(uri) and uri.startswith("file:")
            and not any(char in uri for char in _SHELL_META))


def _deny(reason, *, policy_reason=None):
    return FilesIntentPreview(DENIED, reason, policy_reason=policy_reason)


def compose_files_intent_preview(intent, decision):
    """Reconcile a file-manager intent with a working-directory decision.

    Both inputs are caller-supplied immutable results. A non-matching pair,
    an unsafe field, or a non-allowed working-directory decision yields a
    DENIED record with no path or URI. Source records of the wrong type raise
    ``PreviewInputError`` because that is a host programming error, not a
    launch rejection.
    """
    if not isinstance(intent, FileManagerIntent) or not isinstance(decision, Decision):
        raise PreviewInputError(
            "expected a FileManagerIntent and a Decision source record")
    if not decision.allowed:
        return _deny(REASON_POLICY_DENIED, policy_reason=decision.reason)
    if not _text_ok(intent.action) or intent.action != LAUNCH_ACTION:
        return _deny(REASON_UNSAFE_ACTION)
    if not _uri_ok(intent.uri):
        return _deny(REASON_UNSAFE_URI)
    if not _text_ok(intent.directory):
        return _deny(REASON_INVALID_INPUT)
    if not isinstance(decision.path, str) or not _text_ok(decision.path):
        return _deny(REASON_PATH_MISMATCH)
    if os.path.normcase(intent.directory) != os.path.normcase(decision.path):
        return _deny(REASON_PATH_MISMATCH)
    return FilesIntentPreview(
        APPROVED,
        REASON_OK,
        action=intent.action,
        uri=intent.uri,
        directory=intent.directory,
        policy_reason=decision.reason,
    )
