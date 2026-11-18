"""Unit tests for immutable test execution handoff."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts.run_approved_test_plan import run_plan


COMMIT = "ab" * 20
PLAN = {"version": 1, "repository": "DevTunaSoft/Canopy",
        "commit": COMMIT, "checks": ["unit", "syntax"]}


class ApprovedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "repo"
        self.source.mkdir()
        self.plan = self.base / "approved.json"
        self.plan.write_text(json.dumps(PLAN))
        self.output = self.base / "report.json"

    def test_exact_plan_controls_commands(self):
        verified, executed = [], []
        def validator(plan, checkout):
            verified.append((plan["commit"], checkout))
            return {"status": "PASS"}
        def executor(root, output, checks):
            executed.append((root, output, checks))
            return {"status": "PASS"}
        result = run_plan(self.plan, self.source, self.output,
                          validator=validator, executor=executor)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(verified[0][0], COMMIT)
        self.assertEqual(executed[0][2], ["unit", "syntax"])

    def test_blocks_plan_or_output_inside_checkout(self):
        for plan, output in ((self.source / "approved.json", self.output),
                             (self.plan, self.source / "report.json")):
            with self.subTest(plan=str(plan), output=str(output)), self.assertRaises(ValueError):
                run_plan(plan, self.source, output, validator=lambda *_: {"status": "PASS"})

    def test_blocks_failed_verification_without_executing(self):
        called = []
        with self.assertRaisesRegex(ValueError, "did not pass"):
            run_plan(self.plan, self.source, self.output,
                     validator=lambda *_: {"status": "BLOCKED"},
                     executor=lambda *_: called.append(1))
        self.assertEqual(called, [])

    def test_reject_mutable_commit_and_arbitrary_checks(self):
        self.plan.write_text(json.dumps({**PLAN, "commit": "main"}))
        with self.assertRaises(ValueError):
            run_plan(self.plan, self.source, self.output,
                     validator=lambda *_: {"status": "PASS"})
        self.plan.write_text(json.dumps({**PLAN, "checks": ["shell"]}))
        with self.assertRaises(ValueError):
            run_plan(self.plan, self.source, self.output,
                     validator=lambda *_: {"status": "PASS"})

    def test_prevents_approval_overwrite(self):
        with self.assertRaises(ValueError):
            run_plan(self.plan, self.source, self.plan,
                     validator=lambda *_: {"status": "PASS"})


if __name__ == "__main__":
    unittest.main()
