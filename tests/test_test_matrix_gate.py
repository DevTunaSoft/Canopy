"""Adversarial tests: no single or stale success can certify a Mint scenario."""
import copy
import unittest
from scripts.test_matrix_gate import SCENARIOS, baseline, evaluate


SHA = "ab" * 20
DIGEST = "cd" * 32
RUN = "mint-acceptance-001"


def observations(scenario, *, status="PASS"):
    return [{"oracle": oracle, "status": status, "commit": SHA, "run_id": RUN,
             "artifact_sha256": DIGEST} for oracle in SCENARIOS[scenario]]


class ScenarioGateTests(unittest.TestCase):
    def test_empty_matrix_is_not_pass(self):
        result = evaluate(baseline(), approved_commit=SHA, run_id=RUN)
        self.assertEqual(result["status"], "NOT_RUN")

    def test_two_agreeing_oracles_per_scenario(self):
        report = baseline()
        for entry in report["scenarios"]:
            entry["state"] = "PASS"
            entry["observations"] = observations(entry["id"])
        self.assertEqual(evaluate(report, approved_commit=SHA, run_id=RUN)["status"], "PASS")

    def test_single_oracle_false_green(self):
        report = baseline()
        report["scenarios"][0]["state"] = "PASS"
        report["scenarios"][0]["observations"] = observations("gtk-boot")[:1]
        with self.assertRaisesRegex(ValueError, "independent"):
            evaluate(report, approved_commit=SHA, run_id=RUN)

    def test_oracle_disagreement_is_not_success(self):
        report = baseline()
        report["scenarios"][0]["state"] = "PASS"
        report["scenarios"][0]["observations"] = observations("gtk-boot")
        report["scenarios"][0]["observations"][1]["status"] = "FAIL"
        with self.assertRaises(ValueError):
            evaluate(report, approved_commit=SHA, run_id=RUN)

    def test_stale_run_wrong_commit_and_missing_digest_rejected(self):
        for field, value in (("run_id", "last-run"), ("commit", "ef" * 20),
                             ("artifact_sha256", "")):
            report = baseline()
            report["scenarios"][0]["state"] = "PASS"
            report["scenarios"][0]["observations"] = observations("gtk-boot")
            report["scenarios"][0]["observations"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate(report, approved_commit=SHA, run_id=RUN)

    def test_missing_duplicate_and_unknown_scenarios(self):
        for change in ("missing", "duplicate", "unknown"):
            report = baseline()
            if change == "missing":
                report["scenarios"].pop()
            elif change == "duplicate":
                report["scenarios"][1]["id"] = report["scenarios"][0]["id"]
            else:
                report["scenarios"][0]["id"] = "made-up"
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluate(report, approved_commit=SHA, run_id=RUN)

    def test_blocked_or_failed_never_converts_to_pass(self):
        for state in ("FAIL", "BLOCKED"):
            report = baseline()
            report["scenarios"][0]["state"] = state
            report["scenarios"][0]["observations"] = observations("gtk-boot", status=state)
            self.assertEqual(evaluate(report, approved_commit=SHA, run_id=RUN)["status"], state)

    def test_not_run_with_injected_evidence_is_rejected(self):
        report = baseline()
        report["scenarios"][0]["observations"] = observations("gtk-boot")
        with self.assertRaises(ValueError):
            evaluate(report, approved_commit=SHA, run_id=RUN)


if __name__ == "__main__":
    unittest.main()
