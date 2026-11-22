"""No-network safety tests for the one-command Qt QA wave launcher."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_supervisor import gitops, policy, state
from canopy_supervisor.supervisor import DEFAULT_CONFIG
from tools import canopy_next_wave


class WaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.root = base / "state"
        self.store = state.TaskStore(self.root)
        config = {**DEFAULT_CONFIG, "repo": str(self.repo),
                  "state_root": str(self.root), "max_workers": 3}
        state.atomic_write(self.store.config_path, json.dumps(config))
        self.store.save(self.store.load())
        self.roadmap = self.root / "roadmap.json"
        state.atomic_write(self.roadmap, json.dumps([{
            "id": "old-completed-work", "title": "Previously completed work",
            "objective": "Preserved prior important assignment",
            "scope": ["docs/old.md"], "base": "main",
        }]))
        self.store.set_paused(True)

    def tearDown(self):
        self.temp.cleanup()

    def _prepare(self):
        with patch.object(gitops, "run", return_value=""), \
                patch.object(gitops, "rev_parse", return_value="a" * 40):
            return canopy_next_wave.prepare_wave(self.root)

    def test_appends_three_disjoint_qt_tasks_once(self):
        self.assertEqual(self._prepare(), 3)
        self.assertEqual(self._prepare(), 0)
        items = json.loads(self.roadmap.read_text(encoding="utf-8"))
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0]["id"], "old-completed-work")
        for task in items[1:]:
            self.assertEqual(task["base"], canopy_next_wave.QT_BASE)
            self.assertEqual(task["kind"], "implementation")
            self.assertTrue(task["artifacts"])
            self.assertFalse(policy.protected_violations(
                task["scope"], DEFAULT_CONFIG["protected_paths"]))
        for i, left in enumerate(items[1:]):
            for right in items[i + 2:]:
                self.assertFalse(policy.scope_conflict(left["scope"], right["scope"]))
        self.assertEqual(self.store.load()["tasks"], [],
                         "preparing a wave must not reset task history")

    def test_paused_state_required(self):
        snapshot = self.roadmap.read_bytes()
        self.store.set_paused(False)
        with self.assertRaisesRegex(ValueError, "paused"):
            self._prepare()
        self.assertEqual(self.roadmap.read_bytes(), snapshot)

    def test_active_work_preserved_and_blocks_wave(self):
        data = self.store.load()
        data["tasks"].append({"id": "live", "status": "running"})
        self.store.save(data)
        with self.assertRaisesRegex(ValueError, "active work"):
            self._prepare()
        self.assertEqual(len(json.loads(self.roadmap.read_text())), 1)

    def test_missing_remote_qt_branch_blocks_without_write(self):
        snapshot = self.roadmap.read_bytes()
        with patch.object(gitops, "run", return_value=""), \
                patch.object(gitops, "rev_parse",
                             side_effect=gitops.GitError("missing feature ref")):
            with self.assertRaises(gitops.GitError):
                canopy_next_wave.prepare_wave(self.root)
        self.assertEqual(self.roadmap.read_bytes(), snapshot)

    def test_conflicting_existing_task_must_not_be_overwritten(self):
        task = dict(canopy_next_wave.TASKS[0])
        task["objective"] = "Modified or unsafe existing objective"
        state.atomic_write(self.roadmap, json.dumps([task]))
        with self.assertRaisesRegex(ValueError, "differs"):
            self._prepare()

    def test_missing_roadmap_is_not_silently_replaced(self):
        self.roadmap.unlink()
        with self.assertRaisesRegex(ValueError, "existing roadmap.json required"):
            self._prepare()

    def test_does_not_duplicate_task_already_in_ledger(self):
        data = self.store.load()
        data["tasks"].append({"id": canopy_next_wave.TASKS[0]["id"],
                              "status": "awaiting_review"})
        self.store.save(data)
        self.assertEqual(self._prepare(), 2)
        items = json.loads(self.roadmap.read_text())
        self.assertNotIn(canopy_next_wave.TASKS[0]["id"],
                         [item["id"] for item in items])

    def test_run_until_idle_returns_without_waiting_on_finished_work(self):
        from canopy_supervisor.supervisor import Supervisor
        config = {**DEFAULT_CONFIG, "repo": str(self.repo),
                  "state_root": str(self.root), "auto_queue": False}
        instance = Supervisor(config, self.store, object())
        result = instance.run(until_idle=True)
        self.assertEqual(result["tasks"], [])


if __name__ == "__main__":
    unittest.main()
