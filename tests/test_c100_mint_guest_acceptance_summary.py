"""Offline tests for the fail-closed Mint guest acceptance summary.

No Linux Mint guest, compiled Qt binary, command execution or network access
is used here. These tests check composition of already-observed results only.
"""
import json
import unittest

from canopy_features.mint import guest_acceptance_summary as summary
from canopy_features.mint.guest_acceptance_summary import SummaryError


COMMANDS = {
    "mint_guest_preflight": "python3 tools/mint_guest_preflight.py --json",
    "qt_build": "cmake --build build/classic",
    "mint_qt_smoke": "python3 -m tools.mint_classic_qt_smoke --source-sha abc",
    "evidence_integrity":
        "python3 tools/mint_acceptance_report_gate --evidence-dir /tmp/evidence",
    "runtime_app_launch":
        "canopy-classic-spike --self-test-system-apps-fixture",
}


def record(gate, result, command=None, excerpt="observed command output"):
    return {
        "gate": gate,
        "command": command or COMMANDS[gate],
        "result": result,
        "output_excerpt": excerpt,
    }


def all_pass():
    return [record(gate, "PASS") for gate in summary.REQUIRED_GATES]


class MintGuestAcceptanceSummaryTests(unittest.TestCase):
    def test_empty_results_fail_closed(self):
        result = summary.compose([])
        self.assertEqual(result["status"], "NO_EVIDENCE")
        self.assertEqual(result["missing_gates"], list(summary.REQUIRED_GATES))
        self.assertEqual(result["guest_execution"], "NOT_RUN")
        self.assertEqual(result["mint_guest_acceptance"], "NOT_ESTABLISHED")
        self.assertIs(result["linux_mint_execution_independently_proven"], False)
        self.assertEqual(result["owner_visual_approval"], "NOT_ESTABLISHED")

    def test_skipped_guest_execution_never_becomes_acceptance(self):
        results = [record(gate, "PASS") for gate in summary.REQUIRED_GATES
                   if gate != "mint_qt_smoke"]
        results.append(record("mint_qt_smoke", "SKIPPED",
                              excerpt="no Linux Mint guest available"))
        result = summary.compose(results)
        self.assertEqual(result["status"], "EVIDENCE_INCOMPLETE")
        self.assertEqual(result["guest_execution"], "SKIPPED")
        self.assertEqual(result["skipped_gates"], ["mint_qt_smoke"])
        self.assertEqual(result["missing_gates"], [])
        self.assertEqual(result["mint_guest_acceptance"], "NOT_ESTABLISHED")
        self.assertIs(result["linux_mint_execution_independently_proven"], False)
        self.assertNotIn("ACCEPTED", json.dumps(result))

    def test_not_run_guest_execution_counts_as_skipped(self):
        results = all_pass()
        results[results.index(record("mint_qt_smoke", "PASS"))] = record(
            "mint_qt_smoke", "NOT_RUN")
        result = summary.compose(results)
        self.assertEqual(result["status"], "EVIDENCE_INCOMPLETE")
        self.assertEqual(result["guest_execution"], "SKIPPED")
        self.assertEqual(result["mint_guest_acceptance"], "NOT_ESTABLISHED")

    def test_incomplete_evidence_missing_gates_fail_closed(self):
        results = [record("mint_guest_preflight", "PASS"),
                   record("qt_build", "PASS")]
        result = summary.compose(results)
        self.assertEqual(result["status"], "EVIDENCE_INCOMPLETE")
        self.assertEqual(result["passed_gates"],
                         ["mint_guest_preflight", "qt_build"])
        self.assertEqual(result["missing_gates"], [
            "mint_qt_smoke", "evidence_integrity", "runtime_app_launch",
        ])
        self.assertEqual(result["guest_execution"], "NOT_RUN")
        self.assertEqual(result["mint_guest_acceptance"], "NOT_ESTABLISHED")

    def test_failed_or_blocked_gate_fails_closed(self):
        for failed_status in ("FAIL", "BLOCKED"):
            for gate in summary.REQUIRED_GATES:
                with self.subTest(status=failed_status, gate=gate):
                    results = [record(name, "PASS")
                               for name in summary.REQUIRED_GATES if name != gate]
                    results.append(record(gate, failed_status))
                    result = summary.compose(results)
                    self.assertEqual(result["status"], "EVIDENCE_FAILED")
                    self.assertEqual(result["failed_gates"], [gate])
                    self.assertEqual(result["mint_guest_acceptance"],
                                     "NOT_ESTABLISHED")
                    if gate == "mint_qt_smoke":
                        self.assertEqual(result["guest_execution"], "FAILED")

    def test_all_automated_gates_pass_still_requires_independent_proof(self):
        result = summary.compose(all_pass())
        self.assertEqual(result["status"], "AUTOMATED_GATES_PASS")
        self.assertEqual(result["passed_gates"], list(summary.REQUIRED_GATES))
        self.assertEqual(result["guest_execution"], "COMMAND_RESULT_RECEIVED")
        self.assertIs(result["linux_mint_execution_independently_proven"], False)
        self.assertEqual(result["mint_guest_acceptance"], "NOT_ESTABLISHED")
        self.assertEqual(result["real_application_launch"], "NOT_RUN")
        self.assertEqual(result["compositor_session_switching"], "NOT_RUN")
        self.assertEqual(result["owner_visual_approval"], "NOT_ESTABLISHED")
        for gate in summary.REMAINING_ACCEPTANCE_GATES:
            self.assertIn(gate, result["remaining_acceptance_gates"])

    def test_unknown_or_malformed_records_rejected(self):
        valid = record("qt_build", "PASS")
        bad_records = [
            {"gate": "qt_build", "command": COMMANDS["qt_build"],
             "result": "PASS"},
            dict(valid, extra="field"),
            dict(valid, gate="not_a_gate"),
            dict(valid, result="YES"),
            dict(valid, result=True),
            dict(valid, result=None),
            dict(valid, command="echo unrelated"),
            dict(valid, command=""),
            dict(valid, output_excerpt=123),
            dict(valid, output_excerpt=""),
            dict(valid, output_excerpt="x" * (summary.MAX_EXCERPT_CHARS + 1)),
            "not a record",
        ]
        for bad in bad_records:
            with self.subTest(bad=str(bad)[:40]):
                with self.assertRaises(SummaryError):
                    summary.compose([bad])

    def test_duplicate_gate_rejected(self):
        with self.assertRaisesRegex(SummaryError, "duplicate"):
            summary.compose([record("qt_build", "PASS"),
                             record("qt_build", "FAIL")])

    def test_input_shape_and_size_are_bounded(self):
        for value in (None, "results", {"gate": "qt_build"}):
            with self.subTest(value=value):
                with self.assertRaises(SummaryError):
                    summary.compose(value)
        oversized = [record("qt_build", "PASS")] * (summary.MAX_RESULTS + 1)
        with self.assertRaisesRegex(SummaryError, "too many"):
            summary.compose(oversized)

    def test_command_text_and_excerpt_are_not_echoed(self):
        results = all_pass()
        results[0] = record("mint_guest_preflight", "PASS",
                            excerpt="/home/secret PRIVATE_TOKEN=hidden")
        serialized = json.dumps(summary.compose(results))
        self.assertNotIn("/home/secret", serialized)
        self.assertNotIn("PRIVATE_TOKEN", serialized)
        self.assertNotIn("hidden", serialized)
        self.assertNotIn(COMMANDS["mint_guest_preflight"], serialized)

    def test_composition_is_deterministic(self):
        self.assertEqual(summary.compose(all_pass()), summary.compose(all_pass()))


if __name__ == "__main__":
    unittest.main()
