"""RED/GREEN: supervisor policy must fail closed on wrong-type base/branch."""
import unittest

from canopy_supervisor.policy import PolicyError, validate_task


def _task(**overrides):
    task = {
        "id": "task-001",
        "title": "Valid policy task",
        "objective": "A sufficiently long objective for structural validation.",
        "scope": ["canopy_features/windows/example.py"],
    }
    task.update(overrides)
    return task


class TaskRefTypeGuardTests(unittest.TestCase):
    WRONG = (None, 7, 1.5, True, [], {})

    def test_wrong_base_raises_policy_error(self):
        for value in self.WRONG:
            with self.subTest(value=repr(value)):
                with self.assertRaises(PolicyError):
                    validate_task(_task(base=value))

    def test_wrong_branch_raises_policy_error(self):
        for value in self.WRONG:
            with self.subTest(value=repr(value)):
                with self.assertRaises(PolicyError):
                    validate_task(_task(branch=value))

    def test_no_raw_typeerror_leaks(self):
        with self.assertRaises(PolicyError) as caught:
            validate_task(_task(base=None))
        self.assertNotIsInstance(caught.exception, TypeError)

    def test_valid_refs_still_accepted(self):
        good = validate_task(_task(base="main",
                                   branch="fix/canopy-supervisor-policy-test"))
        self.assertEqual(good["base"], "main")
        self.assertEqual(good["branch"], "fix/canopy-supervisor-policy-test")

    def test_invalid_string_refs_unchanged(self):
        with self.assertRaises(PolicyError):
            validate_task(_task(base="../bad"))
        with self.assertRaises(PolicyError):
            validate_task(_task(branch="bad branch"))


if __name__ == "__main__":
    unittest.main()
