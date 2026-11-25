"""Pure, offline redaction for launch-environment and failure-report data.

This module is a small shared helper, not a desktop service. It reads no real
environment, opens no files or sockets, polls nothing and keeps no state.
Callers pass an explicit mapping or report; output is bounded and deterministic.

Name-based redaction reuses the canonical sensitive vocabulary from
``canopy_core.host_events.FORBIDDEN_FIELDS`` and adds common API-key spellings.
Value-based scrubbing covers free-form log lines that cannot rely on a key.
This does not replace allowlisting: private paths and personal fields should
still be omitted before a report reaches this helper. Wiring this into the
compiled Qt application is a separate, future integration step.
"""
from collections.abc import Mapping
import re

from canopy_core.host_events import FORBIDDEN_FIELDS

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"
MAX_TEXT_BYTES = 512
MAX_ITEMS = 64
MAX_DEPTH = 6


def _name_tokens(name):
    """Split an identifier into lowercase alphanumeric tokens."""
    return frozenset(part for part in re.split(r"[^a-z0-9]+", str(name).lower()) if part)


# Derive from the existing host-event vocabulary, then add key spellings that
# a shell diagnostics dump is likely to encounter.
SENSITIVE_TOKENS = frozenset(
    token for field in FORBIDDEN_FIELDS for token in _name_tokens(field)
) | frozenset({
    "key", "apikey", "passwd", "pwd", "auth", "bearer", "cred", "credentials",
    "xauthority",
})

_SECRET_ASSIGNMENT = re.compile(
    # A preceding underscore is a word character, so \b would miss OPENAI_API_KEY.
    r"(?i)(?<![A-Za-z0-9])(api[_-]?key|apikey|token|secret|password|passwd|pwd|"
    r"credential(?:s)?|authorization|cookie|private[_-]?key|access[_-]?key|bearer)\b"
    r"(\s*[:=]\s*)([\"']?)([^\s\"'&,;]+)"
)
_BEARER_CREDENTIAL = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{1,256}")
_URL_USERINFO = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]{1,15}://)([^/\s:@]+):([^/\s@]{1,256})@"
)


def is_sensitive_name(name):
    """True when an environment or report field name looks credential-like."""
    return bool(_name_tokens(name) & SENSITIVE_TOKENS)


def _replace_assignment(match):
    return match.group(1) + match.group(2) + match.group(3) + REDACTED


def _replace_bearer(match):
    return match.group(1) + " " + REDACTED


def _replace_userinfo(match):
    return match.group(1) + match.group(2) + ":" + REDACTED + "@"


def redact_text(value):
    """Return a bounded, secret-scrubbed string from any scalar value."""
    if isinstance(value, bytes):
        text = value.decode("utf-8", "replace")
    elif value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    # Strip scheme credentials first: otherwise the assignment pass can eat
    # "Bearer" and leave the credential token itself untouched.
    text = _BEARER_CREDENTIAL.sub(_replace_bearer, text)
    text = _SECRET_ASSIGNMENT.sub(_replace_assignment, text)
    text = _URL_USERINFO.sub(_replace_userinfo, text)
    encoded = text.encode("utf-8", "replace")
    if len(encoded) > MAX_TEXT_BYTES:
        return encoded[:MAX_TEXT_BYTES].decode("utf-8", "ignore") + TRUNCATED
    return text


def redact_environment(env):
    """Copy an environment mapping with sensitive values replaced.

    Non-sensitive values are still scrubbed, so a secret pasted into a benign
    field cannot survive. The input mapping is never mutated.
    """
    if not isinstance(env, Mapping):
        raise TypeError("environment must be a mapping")
    result = {}
    for name, value in env.items():
        if not isinstance(name, str):
            raise TypeError("environment variable name must be str")
        result[name] = REDACTED if is_sensitive_name(name) else redact_text(value)
    return result


def redact_report(report, _depth=0):
    """Return a bounded, JSON-friendly copy of a structured failure report."""
    if _depth >= MAX_DEPTH:
        return TRUNCATED
    if isinstance(report, Mapping):
        result = {}
        for index, (key, value) in enumerate(report.items()):
            if index >= MAX_ITEMS:
                result[TRUNCATED] = True
                break
            safe_key = redact_text(key)
            result[safe_key] = (REDACTED if is_sensitive_name(key)
                                else redact_report(value, _depth + 1))
        return result
    if isinstance(report, (list, tuple)):
        items = [redact_report(item, _depth + 1)
                 for item in list(report)[:MAX_ITEMS]]
        if len(report) > MAX_ITEMS:
            items.append(TRUNCATED)
        return items
    return redact_text(report)
