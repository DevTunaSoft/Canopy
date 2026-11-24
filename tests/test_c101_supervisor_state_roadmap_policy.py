"""RED/GREEN: supervisor policy refs and roadmap evidence fail closed."""
import json
import tempfile
import unittest
from pathlib import Path

from canopy_supervisor import roadmap
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


class CampaignEvidenceTypeGuardTests(unittest.TestCase):
    def _campaign(self, payload):
        root = Path(tempfile.mkdtemp())
        folder = root / "evidence" / "task-001"
        folder.mkdir(parents=True)
        (folder / "evidence.json").write_text(json.dumps(payload))
        return roadmap.campaign_status({"id": "task-001"}, root)

    def test_non_object_evidence_fails_closed(self):
        for value in ([], None, 7, "text", True):
            with self.subTest(value=repr(value)):
                self.assertEqual(self._campaign(value), "failed")

    def test_non_list_tests_fails_closed(self):
        self.assertEqual(self._campaign({"tests": 7}), "failed")
        self.assertEqual(self._campaign({"tests": {"result": "PASS"}}), "failed")

    def test_valid_evidence_still_judged(self):
        self.assertEqual(self._campaign({"tests": [{"result": "PASS"}]}), "success")
        self.assertEqual(self._campaign({"tests": [{"result": "FAIL"}]}), "failed")
        self.assertEqual(self._campaign({"tests": [{"result": "NOT RUN"}]}), "blocked")


class BoundedEventHistoryTests(unittest.TestCase):
    def test_event_history_is_bounded(self):
        from canopy_supervisor import state
        from canopy_supervisor.state import TaskStore

        cap = state.MAX_HISTORY_EVENTS
        store = TaskStore(Path(tempfile.mkdtemp()))
        for i in range(cap + 4):
            store.event("task-001", "tick", "n=%d" % i)
        lines = store.history_path.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), cap)
        recent = store.recent_events(3)
        self.assertEqual(len(recent), 3)
        self.assertEqual([row["message"] for row in recent],
                         ["n=%d" % (cap + 3), "n=%d" % (cap + 2), "n=%d" % (cap + 1)])


if __name__ == "__main__":
    unittest.main()
