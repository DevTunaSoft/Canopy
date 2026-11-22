"""Bounded, redacted, structured shell fault ledger.

Host-side, in-memory fault records for Canopy shell components. This module
does not poll, start threads, open sockets, touch the filesystem or run Qt.
It reuses the existing bounded-field rules from ``canopy_core.host_events``
and the QML diagnostic detector from ``tools.qt_smoke`` instead of copying
them. Records are frozen, secret-free and capped so memory stays bounded.

This is an independent component: it is not wired into the compiled Classic
Qt application. Integration (feeding real host faults into ``record`` or
``ingest_stderr``) remains future work.
"""
from collections import deque
from dataclasses import dataclass
import math
import re
from types import MappingProxyType

from canopy_core.host_events import FIELD, FORBIDDEN_FIELDS
from tools.qt_smoke import qml_diagnostics

SCHEMA_VERSION = 1
MAX_RECORDS = 256
MAX_MESSAGE_BYTES = 512
MAX_COMPONENT_BYTES = 64
MAX_CODE_BYTES = 64
MAX_CONTEXT_FIELDS = 8
MAX_CONTEXT_VALUE_BYTES = 256
SEVERITIES = frozenset({"debug", "info", "warning", "error", "critical"})

_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]{0,63}\Z")
_SECRET_PAIR = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|apikey|authorization|"
    r"credential|credentials|cookie|private[_-]?key|access[_-]?key)\b"
    r"(\s*[:=]\s*)([^\s,;]+)")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_REDACTED = "[REDACTED]"
_ELLIPSIS = "…"
# host_events covers the common names; these extend it for shell fault context.
_EXTRA_FORBIDDEN = frozenset({
    "api_key", "apikey", "access_key", "passwd", "credentials", "privatekey",
})


class FaultRecordError(ValueError):
    """Invalid fault input (bad type, bound, severity or context key)."""


def redact(text):
    """Replace secret-bearing assignments and bearer tokens in ``text``."""
    if type(text) is not str:
        raise FaultRecordError("redact expects a str")
    # Strip bearer credentials first: otherwise an "Authorization:" pair rule
    # could consume the word "Bearer" and leave the token itself intact.
    text = _BEARER.sub("Bearer " + _REDACTED, text)
    return _SECRET_PAIR.sub(
        lambda m: m.group(1) + m.group(2) + _REDACTED, text)


def _bound(text, limit):
    """Return ``text`` cut to at most ``limit`` UTF-8 bytes."""
    try:
        data = text.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise FaultRecordError("fault text is not valid UTF-8") from exc
    if len(data) <= limit:
        return text
    return data[: max(0, limit - len(_ELLIPSIS.encode("utf-8")))].decode(
        "utf-8", "ignore") + _ELLIPSIS


def _label(value, limit, what):
    if type(value) is not str or not _LABEL.fullmatch(value):
        raise FaultRecordError("invalid " + what)
    return _bound(value, limit)


def _context_value(key, value):
    if type(value) is str:
        return _bound(redact(value), MAX_CONTEXT_VALUE_BYTES)
    if type(value) is bool or value is None:
        return value
    if type(value) is int:
        if abs(value) > 1_000_000_000_000:
            raise FaultRecordError("context integer exceeds bound")
        return value
    if type(value) is float:
        if not math.isfinite(value) or abs(value) > 1_000_000_000_000:
            raise FaultRecordError("context float is non-finite or unbounded")
        return value
    raise FaultRecordError("nested or untrusted context value for " + key)


def _encode_context(context):
    if context is None:
        return ()
    if type(context) is not dict or len(context) > MAX_CONTEXT_FIELDS:
        raise FaultRecordError("invalid or oversized fault context")
    encoded = []
    for key, value in context.items():
        if (type(key) is not str or not FIELD.fullmatch(key)
                or key.casefold() in FORBIDDEN_FIELDS
                or key.casefold() in _EXTRA_FORBIDDEN):
            raise FaultRecordError("unsupported fault context field name")
        encoded.append((key, _context_value(key, value)))
    return tuple(sorted(encoded))


@dataclass(frozen=True)
class FaultRecord:
    """One immutable, redacted, structured fault record."""

    schema_version: int
    sequence: int
    severity: str
    component: str
    code: str
    message: str
    context: tuple

    @property
    def fields(self):
        """Read-only view of the fault context."""
        return MappingProxyType(dict(self.context))

    def to_dict(self):
        """Plain, exportable snapshot (no live references)."""
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "severity": self.severity,
            "component": self.component,
            "code": self.code,
            "message": self.message,
            "context": dict(self.context),
        }


class RuntimeFaultLedger:
    """Event-driven fault sink with a hard record cap and no background work."""

    def __init__(self, *, capacity=MAX_RECORDS):
        if type(capacity) is not int or not 1 <= capacity <= MAX_RECORDS:
            raise FaultRecordError("invalid ledger capacity")
        self._capacity = capacity
        self._records = deque(maxlen=capacity)
        self._sequence = 0

    def record(self, *, component, code, message, severity="error", context=None):
        """Append one redacted fault record and return it."""
        if type(severity) is not str or severity not in SEVERITIES:
            raise FaultRecordError("unsupported fault severity")
        component = _label(component, MAX_COMPONENT_BYTES, "component")
        code = _label(code, MAX_CODE_BYTES, "code")
        safe_message = _bound(redact(message), MAX_MESSAGE_BYTES)
        safe_context = _encode_context(context)
        self._sequence += 1
        record = FaultRecord(
            SCHEMA_VERSION, self._sequence, severity, component, code,
            safe_message, safe_context,
        )
        self._records.append(record)
        return record

    def ingest_stderr(self, stderr):
        """Turn actionable QML diagnostics from compiled Qt stderr into records.

        Raw bytes are never stored; only the detected diagnostic lines are,
        and each line passes through the same redaction and bounds as any
        other record. No Qt process is launched here.
        """
        records = []
        for line in qml_diagnostics(stderr):
            records.append(self.record(
                component="classic-qt",
                code="qml.diagnostic",
                message=line,
                severity="critical",
            ))
        return tuple(records)

    def snapshot(self):
        """Return an exportable tuple of record dicts, oldest first."""
        return tuple(record.to_dict() for record in self._records)

    @property
    def count(self):
        return len(self._records)

    @property
    def capacity(self):
        return self._capacity
