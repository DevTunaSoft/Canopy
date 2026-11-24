"""Safety regressions for the 100-task Canopy backlog; never launch a worker."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_supervisor import gitops, policy, roadmap, state
from canopy_supervisor.supervisor import DEFAULT_CONFIG
from tools import canopy_backlog_100 as backlog


class CatalogTests(unittest.TestCase):
    def test_exactly_one_hundred_genuine_separate_assignments(self):
        items = backlog.tasks()
        self.assertEqual(len(items), 100)
        self.assertEqual(len({item["id"] for item in items}), 100)
        self.assertEqual(len({p for item in items for p in item["scope"]}), 200)
        self.assertEqual(set(backlog.AREAS), {
            "launcher", "dock", "apps", "windows", "mint", "installer",
            "reliability", "security", "performance", "accessibility",
        })
        for item in items:
            clean = policy.validate_task(item, DEFAULT_CONFIG["protected_paths"])
            self.assertEqual(item, clean)
            self.assertEqual(item["base"], backlog.BASE)
            self.assertEqual(item["kind"], "implementation")
            self.assertEqual(item["scope"], item["artifacts"])
            self.assertTrue(item["tests_required"])
            self.assertIn("Do not modify frozen dock geometry", item["objective"])
            self.assertIn(".canopy-worker-evidence.json", item["objective"])
            self.assertIn("BLOCKED", item["objective"])
            self.assertIn("py -3 -m unittest", item["objective"])

    def test_no_task_overwrites_existing_qt_work(self):
        existing = [
            ["tools/qa/classic_preview_package.py",
             "tests/test_classic_preview_package.py"],
            ["tools/qa/classic_runtime_matrix.py",
             "tests/test_classic_runtime_matrix.py"],
            ["tools/qa/classic_mint_guest_runtime.py",
             "tests/test_classic_mint_guest_runtime.py"],
        ]
        for task in backlog.tasks():
            for paths in existing:
                self.assertFalse(policy.scope_conflict(task["scope"], paths))

    def test_roadmap_accepts_a_hundred_and_rejects_too_many(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = backlog.tasks()
            path = root / "roadmap.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            self.assertEqual(len(roadmap.load(root)), 100)
            path.write_text(json.dumps(catalog + catalog[:29]), encoding="utf-8")
            with self.assertRaisesRegex(roadmap.RoadmapError, "128"):
                roadmap.load(root)

    def test_three_workers_refill_without_duplicates(self):
        items = backlog.tasks()
        pending = []
        seen = set()
        for round_number in range(34):
            new = roadmap.next_tasks(pending, items, 3)
            self.assertLessEqual(len(new), 3)
            for task in new:
                self.assertNotIn(task["id"], seen)
                seen.add(task["id"])
                finished = state.new_task(task, 2)
                finished["status"] = "awaiting_review"
                pending.append(finished)
        self.assertEqual(len(seen), 100)
        self.assertEqual(roadmap.next_tasks(pending, items, 3), [])


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.repo = base / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.root = base / "state"
        self.store = state.TaskStore(self.root)
        config = {**DEFAULT_CONFIG, "repo": str(self.repo),
                  "state_root": str(self.root), "max_workers": 3}
        state.atomic_write(self.store.config_path, json.dumps(config))
        old = state.new_task(policy.validate_task({
            "id": "previous-completed", "title": "Previous code",
            "objective": "Existing accepted work must be kept safe",
            "scope": ["docs/previous.md"],
        }), 2)
        old["status"] = "awaiting_review"
        old["pr"] = {"number": "158"}
        self.store.save({"version": state.STATE_VERSION,
                         "tasks": [old], "updated_at": state.utcnow()})
        self.store.set_paused(True)

    def _prepare(self):
        with patch.object(gitops, "run", return_value=""), \
                patch.object(gitops, "rev_parse", return_value="a" * 40):
            return backlog.prepare(self.root)

    def test_add_once_then_idempotent_with_existing_finished_task(self):
        self.assertEqual(self._prepare(), (100, 100))
        self.assertEqual(self._prepare(), (0, 100))
        self.assertEqual(self.store.load()["tasks"][0]["pr"], {"number": "158"})
        self.assertEqual(len(json.loads((self.root / "roadmap.json").read_text())), 100)

    def test_existing_three_task_roadmap_grows_to_one_hundred_three(self):
        original = [{
            "id": "qt-old-one", "title": "Already completed Qt task",
            "objective": "Preserved prior Qt work", "scope": ["tools/qa/old_one.py"],
        }, {
            "id": "qt-old-two", "title": "Another completed Qt task",
            "objective": "Preserved prior Qt work", "scope": ["tools/qa/old_two.py"],
        }, {
            "id": "qt-old-three", "title": "Third completed Qt task",
            "objective": "Preserved prior Qt work", "scope": ["tools/qa/old_three.py"],
        }]
        p = self.root / "roadmap.json"
        state.atomic_write(p, json.dumps(original))
        self.assertEqual(self._prepare(), (100, 103))
        loaded = roadmap.load(self.root)
        self.assertEqual([i["id"] for i in loaded[:3]],
                         [i["id"] for i in original])

    def test_rejects_live_worker_and_keeps_ledger(self):
        data = self.store.load()
        data["tasks"].append({"id": "live", "status": "running"})
        self.store.save(data)
        with self.assertRaisesRegex(ValueError, "active worker"):
            self._prepare()
        self.assertFalse((self.root / "roadmap.json").exists())

    def test_rejects_unpaused_or_missing_base(self):
        self.store.set_paused(False)
        with self.assertRaisesRegex(ValueError, "pause supervisor"):
            self._prepare()
        self.store.set_paused(True)
        with patch.object(gitops, "run", return_value=""), \
                patch.object(gitops, "rev_parse",
                             side_effect=gitops.GitError("missing")):
            with self.assertRaises(gitops.GitError):
                backlog.prepare(self.root)
        self.assertFalse((self.root / "roadmap.json").exists())

    def test_different_existing_contract_fails_closed(self):
        existing = dict(backlog.tasks()[0])
        existing["objective"] = "unsafe instruction substitution"
        state.atomic_write(self.root / "roadmap.json", json.dumps([existing]))
        with self.assertRaisesRegex(ValueError, "contract has changed"):
            self._prepare()

    def test_duplicate_json_object_keys_rejected_in_roadmap(self):
        # A hostile-but-plausible generator may append a second ``depends_on``
        # field without removing the default. json.loads keeps only the last
        # duplicate key, silently erasing a real prerequisite and publishing an
        # immediately-eligible task instead of a blocked one.
        raw = (
            '[{"id":"hostile-dep","title":"Valid title",'
            '"objective":"A sufficiently long and valid objective text.",'
            '"scope":["docs/hostile_dep.py"],'
            '"depends_on":["previous-completed"],"depends_on":[]}]'
        )
        path = self.root / "roadmap.json"
        state.atomic_write(path, raw)
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            self._prepare()
        self.assertEqual(path.read_bytes(), before)

    def test_128_task_ceiling_protects_existing_catalog(self):
        existing = [{
            "id": f"test-prior-{i:03d}", "title": "Existing task",
            "objective": "Preserve earlier queue", "scope": [f"docs/prior-{i}.md"],
        } for i in range(29)]
        state.atomic_write(self.root / "roadmap.json", json.dumps(existing))
        with self.assertRaisesRegex(ValueError, "128 task"):
            self._prepare()
        self.assertEqual(len(json.loads((self.root / "roadmap.json").read_text())), 29)


if __name__ == "__main__":
    unittest.main()
