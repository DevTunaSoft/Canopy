"""Fail-closed composer for Linux Mint guest acceptance evidence.

Pure, offline component: it runs no commands, starts no services, polls
nothing and makes no network calls. It consumes command-result records that
were produced elsewhere (for example by the Mint preflight, Qt smoke runner
and offline evidence gate) and returns a bounded summary.

The summary never claims that a real Linux Mint guest ran, that the compiled
Qt application was tested, or that an owner approved visuals. Those remain
separate human acceptance gates. A green unit test here is not Mint
acceptance.
"""

SCHEMA_VERSION = 1
MAX_RESULTS = 64
MAX_COMMAND_CHARS = 512
MAX_EXCERPT_CHARS = 8192

RESULT_STATUSES = frozenset({"PASS", "FAIL", "SKIPPED", "BLOCKED", "NOT_RUN"})
FAIL_STATUSES = frozenset({"FAIL", "BLOCKED"})
SKIP_STATUSES = frozenset({"SKIPPED", "NOT_RUN"})
RECORD_KEYS = frozenset({"gate", "command", "result", "output_excerpt"})

# Each gate is bound to the command that must have produced its result, so a
# self-reported label cannot be attached to an unrelated command result.
GATE_COMMANDS = (
    ("mint_guest_preflight", "mint_guest_preflight.py"),
    ("qt_build", "cmake --build"),
    ("mint_qt_smoke", "mint_classic_qt_smoke"),
    ("evidence_integrity", "mint_acceptance_report_gate"),
    ("runtime_app_launch", "--self-test-system-apps-fixture"),
)
REQUIRED_GATES = tuple(name for name, _ in GATE_COMMANDS)
GATE_TOKENS = dict(GATE_COMMANDS)

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


def compose(command_results):
    """Return a fail-closed summary from true command-result records.

    Every record has exactly ``gate``, ``command``, ``result`` and
    ``output_excerpt`` keys. ``result`` is the observed command outcome.
    Unknown, malformed, duplicated or mismatched records raise SummaryError
    instead of being silently ignored or upgraded to a pass.
    """
    if not isinstance(command_results, (list, tuple)):
        raise SummaryError("command results must be a list")
    if len(command_results) > MAX_RESULTS:
        raise SummaryError("too many command results")

    by_gate = {}
    for index, record in enumerate(command_results):
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            raise SummaryError("invalid command result schema at index %d" % index)
        gate = _text(record["gate"], "gate", 64)
        if gate not in GATE_TOKENS:
            raise SummaryError("unknown evidence gate")
        command = _text(record["command"], "command", MAX_COMMAND_CHARS)
        if GATE_TOKENS[gate] not in command:
            raise SummaryError("gate does not match command")
        _text(record["output_excerpt"], "output_excerpt", MAX_EXCERPT_CHARS)
        result = record["result"]
        if not isinstance(result, str) or result not in RESULT_STATUSES:
            raise SummaryError("unknown command result status")
        if gate in by_gate:
            raise SummaryError("duplicate gate")
        by_gate[gate] = result

    missing = [gate for gate in REQUIRED_GATES if gate not in by_gate]
    failed = [gate for gate in REQUIRED_GATES if by_gate.get(gate) in FAIL_STATUSES]
    skipped = [gate for gate in REQUIRED_GATES if by_gate.get(gate) in SKIP_STATUSES]
    passed = [gate for gate in REQUIRED_GATES if by_gate.get(gate) == "PASS"]

    if not command_results:
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
