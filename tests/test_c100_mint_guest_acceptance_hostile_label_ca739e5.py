"""Regression: hostile-but-bounded wrong-type labels in Mint acceptance evidence.

Pure/offline: caller-supplied records are evaluated in memory. No command is
run, no guest is contacted and no network access is used.

``isinstance(value, str)`` admits str subclasses whose comparison behaviour the
caller controls. A bounded label of that type used to be able to claim a PASS
while simultaneously counting as skipped, producing contradictory flags and a
false acceptance claim in the composed summary.
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
    "mint_guest_preflight": "MINT_GUEST_PREFLIGHT_READY_FOR_TESTS: Mint=21.3",
    "qt_build": "[100%] Built target canopy-classic-spike",
    "mint_qt_smoke": "MINT_CLASSIC_QT_SMOKE_PASS: verified",
    "evidence_integrity": '{"status": "PASS"}',
    "runtime_app_launch": "SYSTEM_APP_LAUNCH_FIXTURE_PASS: accepted",
}


class LyingStatus(str):
    """A bounded status label that lies only when compared with PASS."""

    def __eq__(self, other):
        if isinstance(other, str) and other == "PASS":
            return True
        return str.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = str.__hash__


class LyingGate(str):
    """A bounded gate label that impersonates qt_build in an allowlist."""

    def __eq__(self, other):
        if isinstance(other, str) and other == "qt_build":
            return True
        return str.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash("qt_build")


def record(gate, result, excerpt):
    return {
        "gate": gate,
        "command": COMMANDS[gate] if type(gate) is str else COMMANDS["qt_build"],
        "result": result,
        "output_excerpt": excerpt,
    }


class HostileLabelTests(unittest.TestCase):
    def test_lying_result_label_cannot_claim_pass_or_contradict_flags(self):
        # The label's own text is NOT_RUN, but its __eq__ answers True for
        # PASS. The old isinstance() check let it pass the allowlist and then
        # appear in both passed_gates and skipped_gates.
        bad = record("mint_qt_smoke", LyingStatus("NOT_RUN"),
                     PASS_TEXT["mint_qt_smoke"])
        with self.assertRaises(SummaryError):
            summary.compose([bad])

    def test_lying_gate_label_cannot_be_upgraded_to_a_real_gate(self):
        bad = {
            "gate": LyingGate("not-a-gate"),
            "command": COMMANDS["qt_build"],
            "result": "PASS",
            "output_excerpt": PASS_TEXT["qt_build"],
        }
        with self.assertRaises(SummaryError):
            summary.compose([bad])

    def test_plain_string_labels_still_compose(self):
        results = [record(gate, "PASS", PASS_TEXT[gate])
                   for gate in summary.REQUIRED_GATES]
        result = summary.compose(results)
        self.assertEqual(result["status"], "AUTOMATED_GATES_PASS")
        self.assertEqual(result["passed_gates"], list(summary.REQUIRED_GATES))


if __name__ == "__main__":
    unittest.main()
