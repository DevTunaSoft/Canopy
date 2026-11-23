"""Fail-closed composer for Linux Mint guest acceptance evidence.

Pure, offline component. It runs no commands, starts no services, polls
nothing and makes no network calls. It consumes command-result records that
were produced elsewhere (for example by the Mint preflight, the Qt build, the
in-guest Qt smoke runner, the offline evidence gate and the compiled Qt
runtime fixture) and returns a bounded summary.

A PASS record is only accepted when its output excerpt contains the marker
that the corresponding real command prints. That ties the composed summary to
true command results instead of trusting a self-reported label alone.

The result never claims a real Linux Mint guest ran, that the compiled Qt
application was accepted, or that an owner approved visuals. Those remain
separate human acceptance gates. Green unit tests here are not Mint
acceptance.
"""
import re

SCHEMA_VERSION = 1
MAX_RESULTS = 64
MAX_GATE_CHARS = 64
MAX_COMMAND_CHARS = 512
MAX_EXCERPT_CHARS = 8192

RESULT_STATUSES = frozenset({"PASS", "FAIL", "BLOCKED", "SKIPPED", "NOT_RUN"})
FAIL_STATUSES = frozenset({"FAIL", "BLOCKED"})
SKIP_STATUSES = frozenset({"SKIPPED", "NOT_RUN"})
RECORD_KEYS = frozenset({"gate", "command", "result", "output_excerpt"})

# gate, command token, PASS marker pattern, FAIL/BLOCKED marker patterns.
# Markers mirror the literal output of the existing tools and compiled Qt
# source. ``qt_build`` has no stable marker: a non-empty excerpt is required,
# but its text is not interpreted. Patterns are regexes so JSON spacing in
# the offline gate output cannot cause a false mismatch.
GATE_SPECS = (
    ("mint_guest_preflight", "mint_guest_preflight",
     r"MINT_GUEST_PREFLIGHT_READY_FOR_TESTS",
     (r"MINT_GUEST_PREFLIGHT_BLOCKED",)),
    ("qt_build", "cmake --build", None, ()),
    ("mint_qt_smoke", "mint_classic_qt_smoke",
     r"MINT_CLASSIC_QT_SMOKE_PASS",
     (r"MINT_CLASSIC_QT_SMOKE_FAIL", r"MINT_CLASSIC_SMOKE_BLOCKED")),
    ("evidence_integrity", "mint_acceptance_report_gate",
     r'"status"\s*:\s*"PASS"',
     (r"MINT_EVIDENCE_GATE_FAIL:",)),
    ("runtime_app_launch", "--self-test-system-apps-fixture",
     r"SYSTEM_APP_LAUNCH_FIXTURE_PASS",
     (r"SYSTEM_APP_LAUNCH_FIXTURE_FAIL",)),
)
REQUIRED_GATES = tuple(spec[0] for spec in GATE_SPECS)
_COMMAND_TOKENS = {spec[0]: spec[1] for spec in GATE_SPECS}
_PASS_MARKERS = {spec[0]: spec[2] for spec in GATE_SPECS}
_FAIL_MARKERS = {spec[0]: spec[3] for spec in GATE_SPECS}

# No command result can satisfy these. They stay explicit so the summary
# cannot be mistaken for a release or acceptance decision.
REMAINING_ACCEPTANCE_GATES = (
    "independent_linux_mint_execution_proof",
    "real_native_application_launch",
    "compositor_and_session_recovery",
    "owner_visual_approval",
)


class SummaryError(ValueError):
    """Command results cannot be composed into trustworthy evidence."""


def _text(value, field, limit):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise SummaryError("invalid " + field)
    return value


def _matches(pattern, excerpt):
    return re.search(pattern, excerpt) is not None


def _corroborates(gate, result, excerpt):
    """Reject a result label contradicted by the observed command output."""
    pass_marker = _PASS_MARKERS[gate]
    if result == "PASS":
        if pass_marker is not None and not _matches(pass_marker, excerpt):
            raise SummaryError("PASS result lacks command output marker")
        return
    if result in SKIP_STATUSES:
        if pass_marker is not None and _matches(pass_marker, excerpt):
            raise SummaryError("skipped result contradicted by command output")
        return
    fail_markers = _FAIL_MARKERS[gate]
    if fail_markers and not any(_matches(marker, excerpt) for marker in fail_markers):
        raise SummaryError("failed result lacks command output marker")


def compose(command_results):
    """Return a fail-closed summary from true command-result records.

    Each record has exactly ``gate``, ``command``, ``result`` and
    ``output_excerpt`` keys. Unknown, malformed, duplicated, mismatched or
    self-contradictory records raise SummaryError instead of being silently
    ignored or upgraded to a pass. Missing or skipped gates produce a bounded
    non-acceptance summary.
    """
    if not isinstance(command_results, (list, tuple)):
        raise SummaryError("command results must be a list")
    if len(command_results) > MAX_RESULTS:
        raise SummaryError("too many command results")

    by_gate = {}
    for index, record in enumerate(command_results):
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            raise SummaryError("invalid command result schema at index %d" % index)
        gate = _text(record["gate"], "gate", MAX_GATE_CHARS)
        if gate not in _COMMAND_TOKENS:
            raise SummaryError("unknown evidence gate")
        command = _text(record["command"], "command", MAX_COMMAND_CHARS)
        if _COMMAND_TOKENS[gate] not in command:
            raise SummaryError("gate does not match command")
        excerpt = _text(record["output_excerpt"], "output_excerpt", MAX_EXCERPT_CHARS)
        result = record["result"]
        if not isinstance(result, str) or result not in RESULT_STATUSES:
            raise SummaryError("unknown command result status")
        _corroborates(gate, result, excerpt)
        if gate in by_gate:
            raise SummaryError("duplicate gate")
        by_gate[gate] = result

    missing = [gate for gate in REQUIRED_GATES if gate not in by_gate]
    failed = [gate for gate in REQUIRED_GATES if by_gate.get(gate) in FAIL_STATUSES]
    skipped = [gate for gate in REQUIRED_GATES if by_gate.get(gate) in SKIP_STATUSES]
    passed = [gate for gate in REQUIRED_GATES if by_gate.get(gate) == "PASS"]

    if not by_gate:
        status = "NO_EVIDENCE"
    elif failed:
        status = "EVIDENCE_FAILED"
    elif missing or skipped:
        status = "EVIDENCE_INCOMPLETE"
    else:
        status = "AUTOMATED_GATES_PASS"

    smoke = by_gate.get("mint_qt_smoke")
    if smoke is None:
        guest_execution = "NOT_RUN"
    elif smoke in SKIP_STATUSES:
        guest_execution = "SKIPPED"
    elif smoke in FAIL_STATUSES:
        guest_execution = "FAILED"
    else:
        guest_execution = "COMMAND_RESULT_RECEIVED"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mint-guest-acceptance-summary",
        "status": status,
        "gates_total": len(REQUIRED_GATES),
        "passed_gates": passed,
        "failed_gates": failed,
        "skipped_gates": skipped,
        "missing_gates": missing,
        "guest_execution": guest_execution,
        "linux_mint_execution_independently_proven": False,
        "mint_guest_acceptance": "NOT_ESTABLISHED",
        "real_application_launch": "NOT_RUN",
        "compositor_session_switching": "NOT_RUN",
        "owner_visual_approval": "NOT_ESTABLISHED",
        "remaining_acceptance_gates": list(REMAINING_ACCEPTANCE_GATES),
    }
