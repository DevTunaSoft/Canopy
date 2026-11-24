"""Bounded diagnostic text, buffers and JSON report output.

Offline, in-process helpers only. No threads, sockets, timers, filesystem
access or Qt interaction. Integration into the compiled Classic Qt application
remains separate work.
"""
import json

MAX_DIAGNOSTIC_LINE_BYTES = 512
MAX_DIAGNOSTIC_BUFFER_BYTES = 65_536
MAX_REPORT_BYTES = 65_536
TRUNCATION_MARKER = "...[truncated]"


class LogSizeCapError(ValueError):
    """Invalid bound, input type or unserializable report payload."""


class ReportTooLarge(LogSizeCapError):
    """Report serialization exceeded the caller-supplied byte cap."""


def _check_bound(name, value, upper):
    if type(value) is not int or not 1 <= value <= upper:
        raise LogSizeCapError(f"{name} must be an int in 1..{upper}")


def _as_text(value):
    # Require exact builtin types: a bytes/str subclass can override decode()
    # and forge a value that escapes the byte cap or raises a raw builtin
    # exception outside LogSizeCapError.
    if type(value) is bytes:
        # Qt stderr may contain arbitrary bytes; never let decode abort.
        return value.decode("utf-8", "replace")
    if type(value) is str:
        # Lone surrogates become visible escapes, not encoding failures.
        return value.encode("utf-8", "backslashreplace").decode("utf-8")
    raise LogSizeCapError("diagnostic input must be bytes or str")


def _as_utf8(value):
    return _as_text(value).encode("utf-8")


def bound_diagnostic(value, max_bytes=MAX_DIAGNOSTIC_LINE_BYTES):
    """Return sanitized UTF-8 text of at most ``max_bytes`` encoded bytes."""
    _check_bound("max_bytes", max_bytes, MAX_DIAGNOSTIC_BUFFER_BYTES)
    marker = TRUNCATION_MARKER.encode("ascii")
    if max_bytes <= len(marker):
        raise LogSizeCapError("cap too small for truncation marker")
    text = _as_text(value)
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    head = raw[:max_bytes - len(marker)].decode("utf-8", "ignore")
    return head + TRUNCATION_MARKER


class DiagnosticBuffer:
    """Fixed-capacity byte buffer that retains the most recent diagnostics."""

    __slots__ = ("_max_bytes", "_buffer", "dropped_bytes")

    def __init__(self, max_bytes=MAX_DIAGNOSTIC_BUFFER_BYTES):
        _check_bound("max_bytes", max_bytes, MAX_DIAGNOSTIC_BUFFER_BYTES)
        self._max_bytes = max_bytes
        self._buffer = bytearray()
        self.dropped_bytes = 0

    @property
    def size(self):
        return len(self._buffer)

    def feed(self, chunk):
        """Append sanitized bytes, discarding older data when full."""
        data = _as_utf8(chunk)
        if not data:
            return
        room = self._max_bytes - len(self._buffer)
        if len(data) <= room:
            self._buffer.extend(data)
            return
        if room:
            self.dropped_bytes += len(data) - room
            self._buffer.extend(data[-room:])
        else:
            self.dropped_bytes += len(data) + len(self._buffer)
            self._buffer[:] = data[-self._max_bytes:]

    def text(self):
        """Return buffered text; split UTF-8 boundaries become replacements."""
        return self._buffer.decode("utf-8", "replace")

    def clear(self):
        self._buffer.clear()
        self.dropped_bytes = 0


def bounded_json_report(payload, max_bytes=MAX_REPORT_BYTES):
    """Serialize a report to at most ``max_bytes`` ASCII bytes, or fail closed."""
    _check_bound("max_bytes", max_bytes, MAX_REPORT_BYTES)
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=True,
                               allow_nan=False, separators=(",", ":"))
    # ensure_ascii=True above guarantees every emitted chunk is ASCII, so the
    # chunk's str length is already its encoded byte count. Counting with
    # len(piece) avoids allocating one short-lived bytes object per chunk.
    pieces = []
    total = 0
    try:
        for piece in encoder.iterencode(payload):
            total += len(piece)
            if total > max_bytes:
                raise ReportTooLarge(f"JSON report exceeds {max_bytes} bytes")
            pieces.append(piece)
    except ReportTooLarge:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise LogSizeCapError(f"invalid JSON report payload: {exc}") from exc
    return "".join(pieces)
