"""Direct-script invocation of the Mint Qt evidence gate must work.

``python tools/mint_classic_qt_smoke.py --help`` previously failed with
``ModuleNotFoundError: No module named 'tools.mint_guest_preflight'`` because
a directly executed script puts ``tools/`` (not the repository root) on
``sys.path``. Module-style invocation kept working, so the two entry points
disagreed. These are process-level regression tests using only ``--help``:
no VM, no Qt binary, no guest, no screenshots and no asset changes.

CI discovers only ``tests/``; run explicitly with
``python -m unittest tools.qa.mint_smoke_direct_invocation_tests -v``.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "tools" / "mint_classic_qt_smoke.py"
OPTION_RE = re.compile(r"^\s+(--[a-z-]+)", re.MULTILINE)


def run_help(argv, cwd, *, keep_pythonpath=False):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if keep_pythonpath:
        env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable] + argv + ["--help"], cwd=str(cwd), env=env,
        capture_output=True, text=True, timeout=30,
    )


class MintSmokeDirectInvocationTests(unittest.TestCase):
    def test_direct_script_help_succeeds_from_outside_repository(self):
        # A caller must be able to execute the tool by path from any cwd.
        with tempfile.TemporaryDirectory(prefix="canopy-mint-direct-") as td:
            result = run_help([str(SCRIPT)], td)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_module_style_help_still_succeeds(self):
        result = run_help(["-m", "tools.mint_classic_qt_smoke"], REPO, keep_pythonpath=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_both_entry_points_expose_identical_cli_options(self):
        with tempfile.TemporaryDirectory(prefix="canopy-mint-cli-") as td:
            direct = run_help([str(SCRIPT)], td)
        module = run_help(["-m", "tools.mint_classic_qt_smoke"], REPO, keep_pythonpath=True)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(module.returncode, 0, module.stderr)
        self.assertEqual(sorted(set(OPTION_RE.findall(direct.stdout))),
                         sorted(set(OPTION_RE.findall(module.stdout))))
        self.assertIn("Run non-destructive Classic Qt screenshot smoke tests", direct.stdout)
        self.assertIn("Run non-destructive Classic Qt screenshot smoke tests", module.stdout)


if __name__ == "__main__":
    unittest.main()
