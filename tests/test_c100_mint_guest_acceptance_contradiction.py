"""Regression tests: self-contradictory PASS evidence must be rejected.

A command result labelled PASS whose own output excerpt also carries that
gate's FAIL/BLOCKED marker is self-contradictory. The fail-closed composer
must raise SummaryError instead of counting it toward a pass, which would
otherwise let one malformed record escalate a whole summary to
AUTOMATED_GATES_PASS. Pure/offline: no commands or guest access are used.
"""
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
        "canopy-classic-spike --enable-system-apps --self-test-system-apps-fixture",
}

PASS_TEXT = {
    "mint_guest_preflight": "MINT_GUEST_PREFLIGHT_READY_FOR_TESTS: Mint=21.3 Qt=6.4.0",
    "qt_build": "[100%] Built target canopy-classic-spike",
    "mint_qt_smoke": "MINT_CLASSIC_QT_SMOKE_PASS: retry succeeded",
    "evidence_integrity": '{"kind": "integrity", "status": "PASS"}',
    "runtime_app_launch": "SYSTEM_APP_LAUNCH_FIXTURE_PASS: GIO accepted entry",
}
FAIL_TEXT = {
    "mint_guest_preflight": "MINT_GUEST_PREFLIGHT_BLOCKED: not verified as Mint",
    "mint_qt_smoke": "MINT_CLASSIC_QT_SMOKE_FAIL: renderer crashed",
    "evidence_integrity": "MINT_EVIDENCE_GATE_FAIL: screenshot SHA-256 mismatch",
    "runtime_app_launch": "SYSTEM_APP_LAUNCH_FIXTURE_FAIL: GIO launch unsuccessful",
}


def record(gate, result, excerpt):
    return {
        "gate": gate,
        "command": COMMANDS[gate],
        "result": result,
        "output_excerpt": excerpt,
    }


class ContradictoryPassEvidenceTests(unittest.TestCase):
    def test_pass_result_with_failure_marker_is_rejected_for_every_marked_gate(self):
        for gate, fail_text in FAIL_TEXT.items():
            with self.subTest(gate=gate):
                excerpt = fail_text + "\n" + PASS_TEXT[gate]
                with self.assertRaisesRegex(SummaryError, "contradicted"):
                    summary.compose([record(gate, "PASS", excerpt)])

    def test_contradictory_pass_cannot_escalate_summary_to_all_gates_pass(self):
        results = [record(gate, "PASS", PASS_TEXT[gate])
                   for gate in summary.REQUIRED_GATES]
        smoke_index = summary.REQUIRED_GATES.index("mint_qt_smoke")
        results[smoke_index] = record(
            "mint_qt_smoke", "PASS",
            FAIL_TEXT["mint_qt_smoke"] + "\n" + PASS_TEXT["mint_qt_smoke"],
        )
        with self.assertRaises(SummaryError):
            summary.compose(results)

    def test_clean_pass_excerpts_still_compose(self):
        result = summary.compose([record(gate, "PASS", PASS_TEXT[gate])
                                  for gate in summary.REQUIRED_GATES])
        self.assertEqual(result["status"], "AUTOMATED_GATES_PASS")
        self.assertEqual(result["passed_gates"], list(summary.REQUIRED_GATES))

    def test_qt_build_without_stable_marker_is_unaffected(self):
        result = summary.compose([record("qt_build", "PASS", PASS_TEXT["qt_build"])])
        self.assertEqual(result["passed_gates"], ["qt_build"])


if __name__ == "__main__":
    unittest.main()
