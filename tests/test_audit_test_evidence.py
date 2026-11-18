"""Malicious/misleading evidence cases must fail closed."""
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

from scripts.audit_test_evidence import audit, read_report


def good():
    return {
        "schema_version": 1, "status": "PASS",
        "checks": [
            {"name": "unit", "status": "PASS", "exit_code": 0, "duration_seconds": 1.2,
             "output": "Ran 10 tests in 0.03s\n\nOK\n", "output_truncated": False},
            {"name": "syntax", "status": "PASS", "exit_code": 0, "duration_seconds": 0.1,
             "output": "", "output_truncated": False},
            {"name": "gtk", "status": "PASS", "exit_code": 0, "duration_seconds": 2.5,
             "output": "Ran 20 tests in 2.3s\n\nOK\n", "output_truncated": False}
        ]
    }


class EvidenceAuditTests(unittest.TestCase):
    def test_valid_consistent_evidence(self):
        evidence = audit(good())
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["unittest_counts"]["gtk"], 20)

    def test_rejects_misleading_success_states(self):
        changes = [
            lambda d: d.update(status="FAIL"),
            lambda d: d["checks"][0].update(exit_code=1),
            lambda d: d["checks"][0].update(exit_code=False),
            lambda d: d["checks"][0].update(status="BLOCKED"),
            lambda d: d["checks"][0].update(output="OK\n"),
            lambda d: d["checks"][0].update(output="Ran 10 tests in 0.1s\nFAILED (failures=2)"),
            lambda d: d["checks"][0].update(output_truncated=True),
            lambda d: d["checks"][0].pop("output_truncated"),
            lambda d: d["checks"][0].update(duration_seconds=-1),
            lambda d: d["checks"][2].update(output="Ran 20 tests in 1s\nOK (skipped=1)\n"),
            lambda d: d["checks"][2].update(output="Ran 0 tests in 0s\nOK\n"),
            lambda d: d["checks"].pop(),
            lambda d: d["checks"].append(deepcopy(d["checks"][0])),
            lambda d: d.update(schema_version=True),
        ]
        for mutate in changes:
            evidence = good()
            mutate(evidence)
            with self.subTest(mutate=str(mutate)), self.assertRaises(ValueError):
                audit(evidence)

    def test_approved_check_list_must_match_exactly(self):
        self.assertEqual(audit(good(), ["unit", "gtk", "syntax"])["status"], "PASS")
        with self.assertRaises(ValueError):
            audit(good(), ["unit", "gtk"])
        with self.assertRaises(ValueError):
            audit(good(), ["unit", "unknown"])

    def test_real_cinnamon_evidence_requires_two_observers(self):
        sample = good()
        sample["checks"].append({
            "name": "cinnamon", "status": "PASS", "exit_code": 0,
            "duration_seconds": 3.0, "output_truncated": False,
            "output": json.dumps({
                "status": "PASS", "desktop": "Cinnamon X11",
                "window_count": 2, "wmctrl_windows": 2,
                "xdotool_windows": 2, "pid": 425, "polls": 3,
            })
        })
        self.assertEqual(audit(sample, ["unit", "syntax", "gtk", "cinnamon"])["status"], "PASS")
        sample["checks"][-1]["output"] = json.dumps({
            "status": "PASS", "desktop": "Cinnamon X11",
            "window_count": 2, "wmctrl_windows": 1,
            "xdotool_windows": 2, "pid": 425, "polls": 3,
        })
        with self.assertRaisesRegex(ValueError, "Cinnamon"):
            audit(sample, ["unit", "syntax", "gtk", "cinnamon"])

    def test_reject_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text('{"schema_version":1,"schema_version":1,"status":"PASS"}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                read_report(path)
            path.write_bytes(b" " * 300001)
            with self.assertRaisesRegex(ValueError, "Oversized"):
                read_report(path)


if __name__ == "__main__":
    unittest.main()
