"""Execute real passing and failing unittest suites as a test-lab control.

A positive control and deliberate negative control must yield different,
correctly classified process results before other CI results are trusted.
"""
import argparse
from pathlib import Path
import sys
import tempfile

from scripts.mint_testlab import run_check


POSITIVE = """import unittest
class Control(unittest.TestCase):
    def test_known_good(self):
        self.assertEqual(2 + 2, 4)
"""
NEGATIVE = """import unittest
class Control(unittest.TestCase):
    def test_known_bad(self):
        self.assertEqual(2 + 2, 5)
"""


def execute_controls():
    """Use actual subprocess execution, not mock return values."""
    with tempfile.TemporaryDirectory(prefix="canopy-negative-controls-") as tmp:
        root = Path(tmp)
        tests = root / "tests"
        tests.mkdir(mode=0o700)
        source = tests / "test_control.py"
        outcomes = []
        for name, fixture in (("positive", POSITIVE), ("negative", NEGATIVE)):
            source.write_text(fixture, encoding="utf-8")
            check = run_check(
                "unit",
                (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"),
                root, 15)
            outcomes.append({"control": name, "status": check["status"],
                             "exit_code": check.get("exit_code"), "output": check.get("output", "")})
        expected = [("positive", "PASS", 0), ("negative", "FAIL", 1)]
        for actual, (name, status, exit_code) in zip(outcomes, expected):
            if actual["control"] != name or actual["status"] != status:
                raise RuntimeError(f"{name} failed to demonstrate expected {status} behavior")
            if exit_code == 0 and actual["exit_code"] != 0:
                raise RuntimeError("Passing control reported nonzero exit")
            if exit_code != 0 and (type(actual["exit_code"]) is not int or actual["exit_code"] == 0):
                raise RuntimeError("Failing control returned zero exit status")
            output = actual["output"]
            if "Ran 1 test" not in output or (
                ("OK" not in output) if name == "positive" else ("FAILED" not in output)
            ):
                raise RuntimeError(f"{name} did not produce expected unittest output")
        return {"status": "PASS", "positive": "PASS", "injected_failure": "DETECTED",
                "controls": 2, "note": "Real subprocess negative control; not a Mint desktop acceptance test"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Test the test harness using deliberate failures")
    parser.parse_args(argv)
    try:
        outcome = execute_controls()
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS: positive control succeeded and deliberate failing test was detected ({outcome['controls']} controls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
