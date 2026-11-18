"""Verify that positive and adversarial controls actually execute subprocesses."""
import unittest
from unittest.mock import patch

from scripts.negative_controls import execute_controls


class LiveNegativeControlsTests(unittest.TestCase):
    def test_real_python_failing_unittest_detected(self):
        result = execute_controls()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["injected_failure"], "DETECTED")

    def test_false_positive_runner_is_rejected(self):
        with patch("scripts.negative_controls.run_check",
                   return_value={"status": "PASS", "exit_code": 0,
                                 "output": "Ran 1 test in 0s\nOK\n"}):
            with self.assertRaisesRegex(RuntimeError, "negative"):
                execute_controls()


if __name__ == "__main__":
    unittest.main()
