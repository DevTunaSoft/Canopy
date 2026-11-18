import subprocess
import tempfile
import unittest
from scripts.verify_test_plan import validate_plan, verify_checkout


SHA = "ab" * 20
PLAN = {"version": 1, "repository": "DevTunaSoft/Canopy",
        "commit": SHA, "checks": ["unit", "syntax", "gtk"]}


class ApprovedCommitTests(unittest.TestCase):
    def test_good_plan(self):
        self.assertEqual(validate_plan(dict(PLAN))["commit"], SHA)

    def test_reject_mutable_refs_and_unauthorized_checks(self):
        cases = [
            {**PLAN, "commit": "main"},
            {**PLAN, "commit": "A" * 40},
            {**PLAN, "repository": "other/repo"},
            {**PLAN, "version": True},
            {**PLAN, "checks": ["unit", "shell"]},
            {**PLAN, "checks": []},
            {**PLAN, "checks": ["unit", "unit"]},
            {**PLAN, "extra": "unexpected"},
        ]
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_plan(item)

    def test_checkout_exact_match(self):
        with tempfile.TemporaryDirectory() as d:
            def clean_executor(argv, **_kw):
                output = SHA + "\n" if "rev-parse" in argv else ""
                return subprocess.CompletedProcess(argv, 0, output, "")
            result = verify_checkout(PLAN, d, executor=clean_executor)
            self.assertEqual(result["status"], "PASS")
            with self.assertRaises(ValueError):
                verify_checkout(PLAN, d, executor=lambda *_a, **_kw:
                    subprocess.CompletedProcess([], 0, "c" * 40 + "\n", ""))

    def test_reject_dirty_and_untracked_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            for modified in (" M scripts/code.py\n", "?? unexpected.py\n"):
                def executor(argv, **_kw):
                    output = SHA + "\n" if "rev-parse" in argv else modified
                    return subprocess.CompletedProcess(argv, 0, output, "")
                with self.subTest(modified=modified), self.assertRaisesRegex(ValueError, "uncommitted"):
                    verify_checkout(PLAN, d, executor=executor)

    def test_reject_failed_status_check(self):
        with tempfile.TemporaryDirectory() as d:
            def executor(argv, **_kw):
                if "rev-parse" in argv:
                    return subprocess.CompletedProcess(argv, 0, SHA + "\n", "")
                return subprocess.CompletedProcess(argv, 1, "", "broken")
            with self.assertRaisesRegex(ValueError, "clean checkout"):
                verify_checkout(PLAN, d, executor=executor)

    def test_checkout_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                verify_checkout(PLAN, d, executor=lambda *_a, **_kw:
                    subprocess.CompletedProcess([], 1, "", "fatal"))


if __name__ == "__main__":
    unittest.main()
