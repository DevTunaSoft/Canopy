"""Tests for the read-only supervisor recovery auditor."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.supervisor_recovery_audit import (
    audit_all, audit_task, hazard_imports, normalize_worktree)

SAFE_MODULE = '''"""Safe sample state module."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Value:
    number: int
'''

PASSING_TEST = '''"""Sample authored test module."""
import unittest

from canopy_features.demo.sample import Value

class SampleTests(unittest.TestCase):
    def test_value(self):
        self.assertEqual(Value(3).number, 3)
'''

FAILING_TEST = '''"""Sample authored failing test module."""
import unittest

class FailingTests(unittest.TestCase):
    def test_failure(self):
        self.fail("intentional failure")
'''


class ImportPolicyTests(unittest.TestCase):
    def test_urllib_parse_is_a_safe_pure_parser(self):
        source = "from urllib.parse import unquote, urlsplit\n"
        self.assertEqual(hazard_imports(
            "canopy_features/apps/safe_uri_open.py", source), [])

    def test_network_urllib_is_still_rejected(self):
        source = "from urllib.request import urlopen\n"
        self.assertTrue(hazard_imports(
            "canopy_features/apps/safe_uri_open.py", source))

    def test_readonly_mint_argv_probe_is_allowed(self):
        source = ("import subprocess\n"
                  "subprocess.run(['dpkg-query', '-W', name], timeout=2)\n")
        self.assertEqual(hazard_imports(
            "canopy_features/mint/dependency_probe.py", source), [])

    def test_mint_probe_with_shell_is_rejected(self):
        source = "import subprocess\nsubprocess.run(cmd, shell=True)\n"
        self.assertTrue(hazard_imports(
            "canopy_features/mint/dependency_probe.py", source))

    def test_subprocess_outside_mint_is_rejected(self):
        source = "import subprocess\nsubprocess.run(cmd, timeout=2)\n"
        self.assertTrue(hazard_imports(
            "canopy_features/apps/launch_argv.py", source))


class RecoveryAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.worktree = self.base / "worktree"
        self.worktree.mkdir()
        subprocess.run(["git", "init", "-q", str(self.worktree)], check=True,
                       capture_output=True)
        module = self.worktree / "canopy_features" / "demo" / "sample.py"
        module.parent.mkdir(parents=True)
        module.write_text(SAFE_MODULE, encoding="utf-8")
        tests = self.worktree / "tests" / "test_c100_sample.py"
        tests.parent.mkdir(parents=True)
        tests.write_text(PASSING_TEST, encoding="utf-8")
        (tests.parent / "__init__.py").write_text("", encoding="utf-8")
        self.relative_module = "canopy_features/demo/sample.py"
        self.relative_test = "tests/test_c100_sample.py"
        digest = hashlib.sha256(module.read_bytes()).hexdigest()
        self.evidence = {
            "task_id": "sample", "branch": "feat/canopy-supervisor-sample",
            "artifacts": [{"path": self.relative_module, "sha256": digest.upper()}],
            "tests": [{"command": "py -3 -m unittest tests.test_c100_sample -v",
                       "result": "PASS", "output_excerpt": "OK"}],
        }
        self.task = {
            "id": "sample", "branch": "feat/canopy-supervisor-sample",
            "kind": "implementation",
            "worktree": str(self.worktree).replace("\\", "\\\\"),
        }
        self._write_state([self.task])

    def _write_state(self, tasks):
        (self.state / "tasks.json").write_text(json.dumps({"tasks": tasks}),
                                               encoding="utf-8")
        folder = self.state / "evidence" / "sample"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "evidence.json").write_text(json.dumps(self.evidence),
                                              encoding="utf-8")

    def _audit(self, **kwargs):
        return audit_task(self.task, self.state, **kwargs)

    def test_normalizes_historical_doubled_backslashes(self):
        self.assertEqual(normalize_worktree(self.task["worktree"]), self.worktree)

    def test_valid_evidence_is_recoverable(self):
        result = self._audit()
        self.assertEqual(result["status"], "recoverable", result["problems"])
        self.assertEqual(result["problems"], [])
        self.assertIn(self.relative_module, result["paths"])
        self.assertIn(self.relative_test, result["paths"])

    def test_wrong_digest_is_rejected(self):
        self.evidence["artifacts"][0]["sha256"] = "0" * 64
        self._write_state([self.task])
        result = self._audit()
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("artifact_verification" in p for p in result["problems"]))

    def test_visual_path_is_rejected(self):
        (self.worktree / "wallpaper.png").write_bytes(b"fake")
        result = self._audit()
        self.assertTrue(any(p.startswith("visual_path:") for p in result["problems"]))

    def test_out_of_scope_path_is_rejected(self):
        (self.worktree / "top_secret.txt").write_text("x", encoding="utf-8")
        result = self._audit()
        self.assertTrue(any(p.startswith("out_of_scope:") for p in result["problems"]))

    def test_hazardous_import_is_rejected(self):
        module = self.worktree / self.relative_module
        module.write_text("import subprocess\n", encoding="utf-8")
        self.evidence["artifacts"][0]["sha256"] = hashlib.sha256(
            module.read_bytes()).hexdigest()
        self._write_state([self.task])
        result = self._audit()
        self.assertTrue(any(p.startswith("hazard_import:") for p in result["problems"]))

    def test_missing_evidence_is_reported_not_crashed(self):
        (self.state / "evidence" / "sample" / "evidence.json").unlink()
        result = self._audit()
        self.assertEqual(result["status"], "missing_inputs")
        self.assertTrue(result["problems"])

    def test_test_replay_pass(self):
        result = self._audit(run_tests=True)
        self.assertEqual(result["test_replay"]["status"], "PASS")
        self.assertEqual(result["status"], "recoverable")

    def test_test_replay_failure_is_rejected(self):
        (self.worktree / self.relative_test).write_text(FAILING_TEST, encoding="utf-8")
        result = self._audit(run_tests=True)
        self.assertEqual(result["test_replay"]["status"], "FAIL")
        self.assertEqual(result["status"], "rejected")

    def test_disclosed_non_pass_rows_do_not_claim_success(self):
        self.evidence["tests"].append({"command": "py -3 -m unittest tests.other",
                                       "result": "FAIL", "output_excerpt": "known"})
        self._write_state([self.task])
        result = self._audit()
        self.assertEqual(result["status"], "recoverable")
        self.assertTrue(any("FAIL" in item for item in result["disclosed"]))

    def test_audit_all_limit_and_no_mutation(self):
        other = dict(self.task, id="other", worktree=str(self.worktree))
        self._write_state([self.task, other])
        before = (self.state / "tasks.json").read_bytes()
        rows = audit_all(self.state, limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(before, (self.state / "tasks.json").read_bytes())

    def test_invalid_limit_is_rejected(self):
        with self.assertRaises(ValueError):
            audit_all(self.state, limit=0)


if __name__ == "__main__":
    unittest.main()
