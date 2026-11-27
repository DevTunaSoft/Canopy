"""Adapter-backed tests: real git blob input, pure gate, no source mutation."""
import tempfile
import unittest

from tools.qa import stale_base_gate as gate
from tests import stale_base_gate_adapter as adapter


SIBLINGS = (
    "tests/test_alpha.py",
    "tests/test_beta.py",
    "tests/test_gamma.py",
)

BASE_FILES = {
    "tests/test_alpha.py": "assert 'alpha-v1'\n",
    "tests/test_beta.py": "assert 'beta-v1'\n",
}

TIP_FILES = {
    "tests/test_alpha.py": "assert 'alpha-v2'\n",
    "tests/test_beta.py": "assert 'beta-v1'\n",
    "tests/test_gamma.py": "assert 'gamma-v2'\n",
}

STALE_HEAD_FILES = {
    # Branch point blobs: alpha is the pre-sibling version, gamma never existed.
    "tests/test_alpha.py": "assert 'alpha-v1'\n",
    "tests/test_beta.py": "assert 'beta-v1'\n",
    "tests/test_pr_local_change.py": "assert 'local'\n",
}

CURRENT_HEAD_FILES = {
    "tests/test_alpha.py": "assert 'alpha-v2'\n",
    "tests/test_beta.py": "assert 'beta-v1'\n",
    "tests/test_gamma.py": "assert 'gamma-v2'\n",
    "tests/test_local_change.py": "assert 'local'\n",
}


class StaleBaseGateAdapterTests(unittest.TestCase):
    def _build_history(self, root):
        repo = adapter.init_repo(root)
        base = adapter.commit_files(repo, BASE_FILES, "base")
        tip = adapter.commit_files(repo, TIP_FILES, "integration tip adds sibling coverage")
        return repo, base, tip

    def test_real_stale_head_loses_sibling_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, tip = self._build_history(tmp)
            # Head branches from the base, not the current integration tip.
            self.assertEqual(adapter.merge_base(repo, base, tip), base)
            adapter.checkout(repo, base)
            head = adapter.commit_files(repo, STALE_HEAD_FILES, "stale PR head")
            self.assertEqual(adapter.merge_base(repo, head, tip), base)

            snapshot = adapter.collect_snapshot(repo, tip, head, SIBLINGS)
            report = gate.evaluate(snapshot)

            self.assertEqual(report["verdict"], "FAIL")
            self.assertEqual(report["head_sha"], head)
            self.assertEqual(report["integration_tip"], tip)
            self.assertEqual(
                report["findings"],
                [
                    {"code": "SIBLING_ABSENT", "path": "tests/test_gamma.py"},
                    {"code": "SIBLING_CHANGED", "path": "tests/test_alpha.py"},
                    {"code": "STALE_BASE", "path": None},
                ],
            )

    def test_real_current_head_keeps_sibling_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, tip = self._build_history(tmp)
            head = adapter.commit_files(repo, CURRENT_HEAD_FILES, "current PR head")
            self.assertEqual(adapter.merge_base(repo, head, tip), tip)

            snapshot = adapter.collect_snapshot(repo, tip, head, SIBLINGS)
            report = gate.evaluate(snapshot)

            self.assertEqual(report["verdict"], "PASS")
            self.assertEqual(report["findings"], [])
            self.assertEqual(report["head_current"], True)


if __name__ == "__main__":
    unittest.main()
