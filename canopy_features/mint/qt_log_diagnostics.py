"""Offline classification of an already-captured Canopy Classic Qt log buffer.

Pure, stdlib-only analysis. It launches no Qt process, opens no file, polls
nothing and retains no state. The caller owns capture and bounding of the raw
bytes; this module only reads one bounded buffer. Fatal QML pattern detection
has a single owner: :func:`tools.qt_smoke.qml_diagnostics`, reused here rather
than duplicated.

This classifies captured text only. It is not evidence of a real Linux Mint
session, a compiled Qt build, a visible window or a working desktop.
"""
from dataclasses import dataclass

from tools.qt_smoke import qml_diagnostics

READY_MARKER = "CANOPY_CLASSIC_WINDOW_READY"

# Process-termination evidence emitted by Qt/C++ runtime (qFatal, signals).
_CRASH_MARKERS = (
    "Fatal:",
    "FATAL:",
    "ASSERT failure",
    "SIGSEGV",
    "SIGABRT",
    "Segmentation fault",
    "Aborted (core dumped)",
    "This application has requested the Runtime to terminate",
    "qFatal",
)
# Non-QML critical failures emitted by the Classic self-test/C++ host.
_CRITICAL_MARKERS = (
    "SELF_TEST_FAIL:",
    "QML root did not create a visible window",
    "_FAIL:",
)
# Labels for findings reported by the reused qml_diagnostics detector.
_QML_FATAL_MARKERS = (
    "Unable to assign",
    "ReferenceError:",
    "TypeError:",
    "Binding loop detected",
    "QQmlApplicationEngine failed to load component",
)
# Non-fatal notices and opt-in app-launch warnings from SystemAppLauncher.cpp.
_WARNING_MARKERS = (
    "Qt warning:",
    "QML Warning:",
    "CANOPY_APP_LAUNCH_REJECTED:",
    "CANOPY_APP_LAUNCH_FAILED:",
    "CANOPY_APP_LAUNCH_UNAVAILABLE:",
)

SEVERITY_ORDER = ("INCONCLUSIVE", "READY", "WARNING", "FATAL", "CRASH")


@dataclass(frozen=True)
class Finding:
    """One classified log line."""

    category: str
    marker: str
    line: str


@dataclass(frozen=True)
class LogClassification:
    """Structured result for one captured log buffer."""

    severity: str
    ready: bool
    truncated: bool
    findings: tuple

    @property
    def categories(self):
        """Frozenset of finding categories present in this log."""
        return frozenset(finding.category for finding in self.findings)


def _match(markers, line):
    for marker in markers:
        if marker in line:
            return marker
    return None


def classify_log(log):
    """Classify raw captured stdout/stderr ``bytes`` from one Qt run.

    Returns a :class:`LogClassification`. Severity is the worst detected
    issue: CRASH > FATAL > WARNING > READY, or INCONCLUSIVE when no readiness
    marker and no issue is found. Missing readiness and truncation are always
    reported as findings even when a worse severity dominates.
    """
    if not isinstance(log, (bytes, bytearray)):
        raise TypeError("log must be bytes")
    raw = bytes(log)
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()

    truncated = bool(raw) and not raw.endswith((b"\n", b"\r"))
    ready = READY_MARKER in text

    findings = []
    seen = set()

    def add(category, marker, line):
        key = (category, marker, line)
        if key not in seen:
            seen.add(key)
            findings.append(Finding(category, marker, line))

    qml_fatal_lines = set(qml_diagnostics(raw))
    for line in lines:
        marker = _match(_CRASH_MARKERS, line)
        if marker is not None:
            add("crash", marker, line)
            continue
        marker = _match(_CRITICAL_MARKERS, line)
        if marker is not None:
            add("fatal", marker, line)
            continue
        if line in qml_fatal_lines:
            add("qml_fatal", _match(_QML_FATAL_MARKERS, line) or "qml_diagnostic", line)
            continue
        marker = _match(_WARNING_MARKERS, line)
        if marker is not None:
            add("warning", marker, line)

    if not ready:
        add("readiness_missing", READY_MARKER, "")
    if truncated:
        add("truncated", "", lines[-1] if lines else "")

    categories = frozenset(finding.category for finding in findings)
    if "crash" in categories:
        severity = "CRASH"
    elif "fatal" in categories or "qml_fatal" in categories:
        severity = "FATAL"
    elif "warning" in categories:
        severity = "WARNING"
    elif ready:
        severity = "READY"
    else:
        severity = "INCONCLUSIVE"

    return LogClassification(severity, ready, truncated, tuple(findings))
