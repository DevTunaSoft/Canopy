"""Safety and correctness tests for the Canopy multi-agent supervisor."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from canopy_supervisor import credentials, gitops, policy, roadmap, state, worker
from canopy_supervisor.cli import main as cli_main
from canopy_supervisor.supervisor import DEFAULT_CONFIG, Supervisor
from canopy_supervisor.worker import WorkerLauncher


def task_definition(task_id="alpha", scope=None, **extra):
    result = {
        "id": task_id,
        "title": f"Task {task_id}",
        "objective": "Make a bounded, testable improvement inside the owned path.",
        "scope": scope or [f"docs/{task_id}.md"],
        "depends_on": [],
        "base": "main",
        "branch": f"feat/canopy-supervisor-{task_id}",
        "tests_required": True,
    }
    result.update(extra)
    return result


class PolicyTests(unittest.TestCase):
    def test_valid_task(self):
        clean = policy.validate_task(task_definition())
        self.assertEqual(clean["scope"], ["docs/alpha.md"])

    def test_rejects_protected_scope(self):
        with self.assertRaises(policy.PolicyError) as caught:
            policy.validate_task(task_definition(scope=["canopy/assets/icon.png"]))
        self.assertIn("protected", str(caught.exception))

    def test_rejects_absolute_and_traversal_paths(self):
        for bad in ("C:/temp/x", "/etc/passwd", "../secrets"):
            with self.subTest(bad=bad), self.assertRaises(policy.PolicyError):
                policy.validate_task(task_definition(scope=[bad]))

    def test_scope_conflict_detection(self):
        self.assertTrue(policy.scope_conflict(["docs/a.md"], ["docs/*"]))
        self.assertTrue(policy.scope_conflict(["tests/unit/x.py"], ["tests/unit/x.py"]))
        self.assertFalse(policy.scope_conflict(["docs/a.md"], ["tests/test_a.py"]))

    def test_evidence_requires_real_tests_and_draft(self):
        task = policy.validate_task(task_definition())
        evidence = {
            "task_id": task["id"], "branch": task["branch"], "commit_sha": "PENDING",
            "tests": [{"command": "python -m unittest tests.test_x", "result": "PASS",
                       "output_excerpt": "OK"}],
            "draft": True,
        }
        policy.validate_evidence(evidence, task, ["docs/alpha.md"], pending_allowed=True)
        with self.assertRaises(policy.PolicyError):
            policy.validate_evidence(evidence, task, ["docs/alpha.md"])
        evidence["draft"] = False
        with self.assertRaises(policy.PolicyError):
            policy.validate_evidence(evidence, task, ["docs/alpha.md"], pending_allowed=True)
        evidence["draft"] = True
        evidence["tests"][0]["result"] = "FAIL"
        with self.assertRaises(policy.PolicyError):
            policy.validate_evidence(evidence, task, ["docs/alpha.md"], pending_allowed=True)

    def test_evidence_rejects_out_of_scope_changes(self):
        task = policy.validate_task(task_definition())
        evidence = {
            "task_id": task["id"], "branch": task["branch"], "commit_sha": "a" * 40,
            "tests": [{"command": "pytest", "result": "PASS", "output_excerpt": "1 passed"}],
            "draft": True,
        }
        with self.assertRaises(policy.PolicyError) as caught:
            policy.validate_evidence(evidence, task, ["canopy/assets/secret.png"])
        self.assertIn("outside task scope", str(caught.exception))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "state"
        self.store = state.TaskStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_atomic_write_and_load(self):
        state.atomic_write(self.root / "config.json", '{"a": 1}\n')
        self.assertEqual(state.read_json(self.root / "config.json", {}), {"a": 1})
        data = self.store.load()
        self.assertEqual(data["version"], state.STATE_VERSION)
        self.assertEqual(data["tasks"], [])
        self.store.save(data)
        self.assertEqual(self.store.load()["tasks"], [])

    def test_corrupt_state_is_not_silently_replaced(self):
        (self.root / "tasks.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.load()

    def test_exclusive_lock_rejects_second_owner(self):
        with state.exclusive_lock(self.store.lock_path):
            with self.assertRaises(state.LockBusy):
                with state.exclusive_lock(self.store.lock_path):
                    pass

    def test_events_and_dashboard(self):
        data = self.store.load()
        data["tasks"].append(state.new_task(task_definition(), 2))
        self.store.save(data)
        self.store.event("alpha", "launched", "pid=42", worker="worker-1")
        dashboard = self.store.dashboard(data, DEFAULT_CONFIG)
        self.assertIn("alpha", dashboard)
        self.assertIn("launched", dashboard)
        self.assertIn("worker-1", dashboard)

    def test_pause_flag(self):
        self.assertFalse(self.store.paused)
        self.store.set_paused(True)
        self.assertTrue(self.store.paused)
        self.store.set_paused(False)
        self.assertFalse(self.store.paused)


class CredentialTests(unittest.TestCase):
    def test_explicit_and_environment_credentials_win(self):
        self.assertEqual(credentials.get_opencode_api_key("explicit"), "explicit")
        with patch.dict(os.environ, {"OPENCODE_API_KEY": "from-env"}):
            self.assertEqual(credentials.get_opencode_api_key(), "from-env")

    def test_reads_active_opencode_credential_from_isolated_db(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "opencode.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "create table credential (integration_id text, active integer, value text)"
            )
            connection.execute(
                "insert into credential values (?,?,?)",
                ("opencode", 1, json.dumps({"type": "oauth", "access": "test-access"})),
            )
            connection.commit()
            connection.close()
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(credentials.get_opencode_api_key(data_home=base),
                                 "test-access")

    def test_missing_installation_raises_without_token_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(credentials.CredentialError):
                    credentials.get_opencode_api_key(data_home=Path(directory))


class RoadmapTests(unittest.TestCase):
    def test_refills_pipeline_without_duplicates(self):
        items = [task_definition(f"road-{index}") for index in range(4)]
        live = state.new_task(task_definition("road-0"), 2)
        live["status"] = "running"
        chosen = roadmap.next_tasks([live], items, 3)
        self.assertEqual([task["id"] for task in chosen], ["road-1", "road-2"])

    def test_conflicting_scope_and_unmet_dependency_are_skipped(self):
        items = [
            task_definition("first", scope=["docs/shared.md"]),
            task_definition("second", scope=["docs/shared.md"]),
            task_definition("third", depends_on=["first"]),
        ]
        chosen = roadmap.next_tasks([], items, 3)
        self.assertEqual([task["id"] for task in chosen], ["first"])

    def test_blocked_campaign_is_paused_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = state.new_task(task_definition("blocked-task"), 2)
            task.update({"campaign": "qt-toolchain-enablement", "status": "awaiting_review"})
            evidence = root / "evidence" / "blocked-task"
            evidence.mkdir(parents=True)
            (evidence / "evidence.json").write_text(json.dumps({
                "tests": [{"result": "BLOCKED", "command": "probe"}],
            }), encoding="utf-8")
            self.assertEqual(roadmap.campaign_status(task, root), "blocked")
            chosen = roadmap.generate([task], 3, state_root=root)
            self.assertNotIn("qt-toolchain-enablement", [t["campaign"] for t in chosen])

    def test_blocked_prerequisites_roll_over_to_unblocked_code_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = []
            for index, campaign in enumerate(roadmap.CAMPAIGNS[:6]):
                task_id = f"blocked-prereq-{index}"
                item = state.new_task(task_definition(task_id), 2)
                item.update({"campaign": campaign["id"], "status": "blocked"})
                folder = root / "evidence" / task_id
                folder.mkdir(parents=True)
                (folder / "evidence.json").write_text(
                    json.dumps({"tests": [{"command": "probe", "result": "BLOCKED"}]}),
                    encoding="utf-8")
                prior.append(item)
            chosen = roadmap.generate(prior, 3, state_root=root)
            self.assertEqual([item["campaign"] for item in chosen], [
                "shared-event-queue", "shell-host-fault-matrix",
                "registry-negative-controls",
            ])
            self.assertTrue(all(item["kind"] == "implementation" for item in chosen))
            self.assertTrue(all(item["artifacts"] for item in chosen))
            scopes = [path for item in chosen for path in item["scope"]]
            self.assertEqual(len(scopes), len(set(scopes)))
            # Once dispatched, independently owned scopes aren't assigned again.
            active = [state.new_task(item, 2) for item in chosen]
            for item in active:
                item["status"] = "running"
            follow_up = roadmap.generate(prior + active, 4, state_root=root)
            self.assertEqual([item["campaign"] for item in follow_up],
                             ["screenshot-provenance-gate"])

    def test_generate_prioritizes_real_work_and_caps_campaigns(self):
        first = roadmap.generate([], 3)
        self.assertEqual([task["campaign"] for task in first], [
            "qt-toolchain-enablement", "qt-source-build", "qt-runtime-screenshot",
        ])
        self.assertTrue(all(task["kind"] in ("build", "verify") for task in first))
        exhausted = []
        for number in (1, 2):
            item = task_definition(f"mint-guest-acceptance-attempt-{number}")
            item.update({"campaign": "mint-guest-acceptance", "status": "failed",
                         "attempts": 1, "next_attempt_at": 0})
            exhausted.append(item)
        selected = roadmap.generate(exhausted, 3)
        self.assertNotIn("mint-guest-acceptance", [task["campaign"] for task in selected])

    def test_custom_roadmap_file_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "roadmap.json").write_text(json.dumps([task_definition("custom")]),
                                               encoding="utf-8")
            loaded = roadmap.load(root)
        self.assertEqual([task["id"] for task in loaded], ["custom"])


class GitOpsTests(unittest.TestCase):
    def test_draft_pr_command_never_merges(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gitops, "run", side_effect=lambda args, **kw: calls.append(args) or
                              "https://github.com/DevTunaSoft/Canopy/pull/7"):
                url = gitops.create_draft_pr(
                    root, repo_slug="DevTunaSoft/Canopy", base="main", head="feat/x",
                    title="DRAFT: x", body="body", body_dir=root,
                )
            self.assertEqual(url, "https://github.com/DevTunaSoft/Canopy/pull/7")
        self.assertIn("--draft", calls[0])
        joined = " ".join(calls[0]).lower()
        self.assertNotIn("merge", joined)

    def test_commit_all_stages_and_commits_with_local_identity(self):
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            if args == ["git", "diff", "--cached", "--name-only"]:
                return "docs/a.md"
            return "a" * 40 if args[-1] == "HEAD" else ""

        with patch.object(gitops, "pending_files", return_value=["docs/a.md"]), \
                patch.object(gitops, "run", side_effect=fake_run):
            sha = gitops.commit_all(Path("."), "test commit")
        self.assertEqual(sha, "a" * 40)
        self.assertIn(["git", "add", "-A", "--", ".", *gitops.PYTHON_CACHE_PATHSPECS], calls)
        self.assertTrue(any("user.name=Canopy Supervisor" in arg for call in calls for arg in call))

    def test_python_cache_ignored_only_when_untracked_and_never_staged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gitops.run(["git", "init"], cwd=root)
            gitops.run(["git", "-c", "user.name=Test", "-c", "user.email=t@t",
                        "commit", "--allow-empty", "-m", "initial"], cwd=root)
            code = root / "canopy_core" / "event_queue.py"
            code.parent.mkdir()
            code.write_text("def enqueue(): return True\n", encoding="utf-8")
            cache = root / "canopy_core" / "__pycache__" / "__init__.cpython-314.pyc"
            cache.parent.mkdir()
            cache.write_bytes(b"garbage-bytecode")
            other = root / "canopy_core" / "unexpected.py"
            other.write_text("unexpected change\n", encoding="utf-8")
            self.assertEqual(gitops.pending_files(root),
                             ["canopy_core/event_queue.py", "canopy_core/unexpected.py"])
            other.unlink()
            self.assertEqual(gitops.pending_files(root), ["canopy_core/event_queue.py"])
            gitops.commit_all(root, "feat: event queue")
            self.assertIn("canopy_core/event_queue.py",
                          gitops.run(["git", "show", "--pretty=format:", "--name-only", "HEAD"],
                                     cwd=root).splitlines())
            self.assertNotIn("canopy_core/__pycache__/__init__.cpython-314.pyc",
                             gitops.run(["git", "show", "--pretty=format:", "--name-only", "HEAD"],
                                        cwd=root).splitlines())
            self.assertTrue(cache.exists(), "do not delete the user's cache files")

    def test_staged_out_of_scope_file_remains_visible_to_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gitops.run(["git", "init"], cwd=root)
            gitops.run(["git", "-c", "user.name=Test", "-c", "user.email=t@t",
                        "commit", "--allow-empty", "-m", "initial"], cwd=root)
            own = root / "docs" / "alpha.md"
            own.parent.mkdir()
            own.write_text("safe change", encoding="utf-8")
            secret = root / "canopy" / "assets" / "art.png"
            secret.parent.mkdir(parents=True)
            secret.write_bytes(b"not approved")
            gitops.run(["git", "add", str(secret.relative_to(root))], cwd=root)
            changed = gitops.pending_files(root)
            self.assertIn("canopy/assets/art.png", changed)
            task = policy.validate_task(task_definition("alpha"))
            evidence = {"task_id": "alpha", "branch": task["branch"],
                        "commit_sha": "PENDING",
                        "tests": [{"command": "python -m unittest", "result": "PASS",
                                   "output_excerpt": "OK"}], "draft": True}
            with self.assertRaises(policy.PolicyError):
                policy.validate_evidence(evidence, task, changed, pending_allowed=True)

    def test_worktree_add_uses_branch_and_base_commit(self):
        calls = []
        with patch.object(gitops, "branch_exists", return_value=False), \
                patch.object(gitops, "run", side_effect=lambda args, **kw: calls.append(args) or ""), \
                tempfile.TemporaryDirectory() as directory:
            gitops.worktree_add(Path(directory), Path(directory) / "wt", "feat/x", "b" * 40)
        self.assertIn("-b", calls[0])
        self.assertIn("b" * 40, calls[0])

    def test_invalid_pid_is_not_alive(self):
        self.assertFalse(gitops.is_pid_alive(-1))

    @unittest.skipUnless(os.name == "nt", "requires Windows process handles")
    def test_native_windows_pid_liveness_before_and_after_exit(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(6)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            self.assertTrue(gitops.is_pid_alive(proc.pid),
                            "a live Windows child must not be misclassified as lost")
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        self.assertFalse(gitops.is_pid_alive(proc.pid))


class WorkerTests(unittest.TestCase):
    def test_redaction_removes_credentials_and_ansi(self):
        text = "\x1b[31mtoken ghp_" + "a" * 30 + " OPENCODE_API_KEY=st_" + "b" * 30
        cleaned = worker.redact(text)
        self.assertNotIn("ghp_", cleaned)
        self.assertNotIn("st_", cleaned)
        self.assertNotIn("\x1b", cleaned)
        self.assertIn("[REDACTED]", cleaned)

    def test_prompt_is_scoped_and_does_not_load_history(self):
        task = policy.validate_task(task_definition())
        prompt = worker.build_prompt(task, Path("/worktree"), Path("/evidence.json"),
                                     tuple(policy.PROTECTED_PATHS))
        self.assertIn("docs/alpha.md", prompt)
        self.assertIn(task["branch"], prompt)
        self.assertIn("Do not load full git history", prompt)
        self.assertNotIn("git log", prompt)

    def test_implementation_prompt_requires_file_hash_evidence(self):
        task = policy.validate_task({
            **task_definition("code"),
            "kind": "implementation",
            "artifacts": ["canopy_core/event_queue.py"],
        })
        prompt = worker.build_prompt(task, Path("/worktree"), Path("/evidence.json"),
                                     tuple(policy.PROTECTED_PATHS))
        self.assertIn("array of {path, sha256} objects", prompt)
        self.assertIn("supervisor owns task rollover", prompt)
        self.assertIn("Do not fabricate assets or approval", prompt)

    def test_worker_prompt_uses_in_worktree_evidence_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worktree = root / "worktree"
            worktree.mkdir()
            task = policy.validate_task(task_definition())
            launcher = WorkerLauncher(
                {"model": "opencode-go/hy4-flash-free"}, root,
                credential=lambda: "test-token", opencode_exe="opencode",
                spawner=lambda args, **kw: SimpleNamespace(pid=1234),
            )
            launcher.launch(task, "worker-1", worktree, root / "worker.log")
            text = (root / "worker.log").read_text(encoding="utf-8")
            self.assertIn("LAUNCH", text)
            prompt = worker.build_prompt(
                task, worktree, worker.worker_evidence_path(worktree),
                tuple(policy.PROTECTED_PATHS),
            )
            self.assertIn(str(worktree / ".canopy-worker-evidence.json"), prompt)
            self.assertNotIn(str(root / "evidence" / task["id"]), prompt)
            self.assertIn("Never write outside", prompt)

    def test_environment_is_isolated_per_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = WorkerLauncher({}, root, credential=lambda: "test-token")
            env_a = launcher.build_env("worker-1")
            env_b = launcher.build_env("worker-2")
        self.assertEqual(env_a["OPENCODE_API_KEY"], "test-token")
        self.assertNotEqual(env_a["XDG_DATA_HOME"], env_b["XDG_DATA_HOME"])
        self.assertIn("worker-1", env_a["XDG_DATA_HOME"])

    def test_launch_uses_opencode_run_with_go_model(self):
        calls = []
        fake_process = SimpleNamespace(pid=4242)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worktree = root / "wt"
            worktree.mkdir()
            config = {"model": "opencode-go/hy4-flash-free"}
            launcher = WorkerLauncher(
                config, root, credential=lambda: "test-token", opencode_exe="opencode.exe",
                spawner=lambda *a, **k: calls.append((a, k)) or fake_process,
            )
            task = policy.validate_task(task_definition())
            pid = launcher.launch(task, "worker-1", worktree, root / "log.txt")
        self.assertEqual(pid, 4242)
        args = calls[0][0][0]
        self.assertIn("--pure", args)
        self.assertIn("run", args)
        self.assertIn("opencode-go/hy4-flash-free", args)
        self.assertIn(str(worktree), args)

    def test_progress_signature_tracks_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worktree = root / "wt"
            worktree.mkdir()
            log = root / "log.txt"
            log.write_text("start", encoding="utf-8")
            before = worker.progress_signature(worktree, log)
            (worktree / "note.md").write_text("new", encoding="utf-8")
            self.assertNotEqual(before, worker.progress_signature(worktree, log))


class FakeGit:
    """In-memory stand-in with a complete audit trail of publish commands."""

    def __init__(self):
        self.calls = []
        self.pr_url = "https://github.com/DevTunaSoft/Canopy/pull/55"
        self.changed = ["docs/alpha.md"]
        self.pending = ["docs/alpha.md"]
        self.commit = "c" * 40
        self.alive = set()
        self.fail_commit = False

    class GitError(RuntimeError):
        pass

    def rev_parse(self, repo, ref):
        self.calls.append(("rev_parse", ref))
        return "b" * 40

    def worktree_list(self, repo):
        self.calls.append(("worktree_list",))
        return []

    def branch_exists(self, repo, branch):
        self.calls.append(("branch_exists", branch))
        return False

    def worktree_add(self, repo, path, branch, base_sha):
        self.calls.append(("worktree_add", branch))
        Path(path).mkdir(parents=True, exist_ok=True)
        return Path(path)

    def run(self, args, **kwargs):
        self.calls.append(("run", tuple(args)))
        return ""

    def pending_files(self, worktree):
        self.calls.append(("pending_files",))
        return list(self.pending)

    def changed_files(self, worktree, base_sha):
        self.calls.append(("changed_files",))
        return list(self.changed)

    def commit_all(self, worktree, message):
        self.calls.append(("commit_all", message))
        if self.fail_commit:
            raise self.GitError("nothing to commit")
        return self.commit

    def push_branch(self, worktree, branch, remote):
        self.calls.append(("push", branch, remote))

    def find_open_pr(self, worktree, **kwargs):
        self.calls.append(("find_pr", kwargs["head"]))
        return None

    def create_draft_pr(self, worktree, **kwargs):
        self.calls.append(("draft_pr", kwargs["head"], kwargs["base"]))
        return self.pr_url

    def is_pid_alive(self, pid):
        return pid in self.alive

    def terminate_pid(self, pid):
        self.calls.append(("terminate", pid))
        self.alive.discard(pid)


class FakeLauncher:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code
        self.pid = 100
        self.launched = []

    def launch(self, task, worker_id, worktree, log_path):
        self.pid += 1
        self.launched.append((task["id"], worker_id, self.pid))
        return self.pid

    def knows(self, pid):
        return False

    def poll(self, pid):
        return self.exit_code


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.root = base / "state"
        self.store = state.TaskStore(self.root)
        self.config = {**DEFAULT_CONFIG, "repo": str(self.repo), "state_root": str(self.root),
                       "max_workers": 2, "poll_seconds": 1}
        self.git = FakeGit()
        self.launcher = FakeLauncher()
        self.supervisor = Supervisor(self.config, self.store, self.launcher, git=self.git,
                                     now_fn=lambda: 1000.0)

    def tearDown(self):
        self.temp.cleanup()

    def _add(self, definition):
        clean = policy.validate_task(definition, self.config["protected_paths"])
        task = state.new_task(clean, self.config["max_attempts"])
        data = self.store.load()
        data["tasks"].append(task)
        self.store.save(data)
        return task["id"]

    def _get(self, task_id):
        return next(task for task in self.store.load()["tasks"] if task["id"] == task_id)

    def _mutate(self, task_id, **fields):
        data = self.store.load()
        task = next(item for item in data["tasks"] if item["id"] == task_id)
        task.update(fields)
        self.store.save(data)

    def _write_evidence(self, task_id, commit="PENDING", result="PASS", extra=None):
        directory = self.root / "evidence" / task_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "evidence.json").write_text(json.dumps({
            "task_id": task_id, "branch": f"feat/canopy-supervisor-{task_id}",
            "commit_sha": commit,
            "tests": [{"command": "python -m unittest tests.test_x", "result": result,
                       "output_excerpt": "OK"}],
            "changed_files": [f"docs/{task_id}.md"], "draft": True,
            "notes": "bounded task", **(extra or {}),
        }), encoding="utf-8")

    def test_dispatch_reserves_workers_and_respects_limit(self):
        for name in ("alpha", "beta", "gamma"):
            self._add(task_definition(name))
        data = self.store.load()
        self.assertEqual(self.supervisor.dispatch(data), 2)
        self.assertEqual(self.supervisor.dispatch(data), 0)
        statuses = [self._get(name)["status"] for name in ("alpha", "beta", "gamma")]
        self.assertEqual(statuses, ["running", "running", "queued"])
        owners = [self._get(name)["owner"] for name in ("alpha", "beta")]
        self.assertEqual(len(set(owners)), 2)

    def test_dispatch_blocks_scope_conflict_and_pending_dependency(self):
        self._add(task_definition("alpha", scope=["docs/shared.md"]))
        self._add(task_definition("beta", scope=["docs/shared.md"], depends_on=["alpha"]))
        data = self.store.load()
        self.assertEqual(self.supervisor.dispatch(data), 1)
        self.assertEqual(self._get("beta")["status"], "queued")

    def test_paused_supervisor_dispatches_nothing(self):
        self._add(task_definition("alpha"))
        self.store.set_paused(True)
        self.assertEqual(self.supervisor.dispatch(self.store.load()), 0)

    def test_known_worker_exit_is_verified_before_pid_loss_recovery(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha")
        self.launcher.exit_code = 0
        # The child exited just before this supervisor tick. The OS no
        # longer considers the PID live, but Popen still knows its exit code.
        with patch.object(self.launcher, "knows", return_value=True):
            data = self.store.load()
            self.assertEqual(self.supervisor.recover(data), 0)
            self.assertEqual(self.supervisor.monitor(data), 1)
            self.assertEqual(data["tasks"][0]["status"], "verifying")
            self.assertEqual(data["tasks"][0]["exit_code"], 0)
            self.supervisor.verify(data)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "awaiting_review")
        self.assertFalse(any(row[0] == "terminate" for row in self.git.calls))
        self.assertEqual(self._get("alpha")["attempts"], 1)

    def test_known_worker_crash_keeps_real_exit_code_instead_of_retrying(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self.launcher.exit_code = 7
        with patch.object(self.launcher, "knows", return_value=True):
            data = self.store.load()
            self.assertEqual(self.supervisor.recover(data), 0)
            self.assertEqual(self.supervisor.monitor(data), 1)
            self.assertEqual(data["tasks"][0]["exit_code"], 7)
            self.supervisor.verify(data)
        self.store.save(data)
        task = self._get("alpha")
        self.assertEqual(task["status"], "failed")
        self.assertIn("worker did not write evidence JSON", task["last_error"])
        self.assertEqual(task["attempts"], 1)
        self.assertFalse(any(call[0] == "draft_pr" for call in self.git.calls))

    def test_verifying_state_survives_exited_pid_during_recovery(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha")
        self._mutate("alpha", status="verifying", pid=555, lease_expires_at=0.0)
        data = self.store.load()
        self.assertEqual(self.supervisor.recover(data), 0)
        self.assertEqual(data["tasks"][0]["status"], "verifying")
        self.supervisor.verify(data)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "awaiting_review")

    def test_worktree_evidence_is_staged_and_deleted_before_publish(self):
        self._add(task_definition("alpha"))
        self.supervisor.config["auto_queue"] = False
        self.supervisor.dispatch(self.store.load())
        worktree = Path(self._get("alpha")["worktree"])
        source = worker.worker_evidence_path(worktree)
        source.write_text(json.dumps({
            "task_id": "alpha",
            "branch": "feat/canopy-supervisor-alpha",
            "commit_sha": "PENDING",
            "tests": [{"command": "python -m unittest", "result": "PASS",
                       "output_excerpt": "OK"}],
            "changed_files": ["docs/alpha.md"], "draft": True,
            "notes": "actual test result",
        }), encoding="utf-8")
        self.launcher.exit_code = 0
        data = self.supervisor.step()
        self.assertEqual(data["tasks"][0]["status"], "awaiting_review")
        self.assertFalse(source.exists(), "ephemeral worktree evidence must be removed")
        durable = worker.evidence_path(self.root, "alpha")
        self.assertTrue(durable.is_file())
        self.assertEqual(json.loads(durable.read_text())["task_id"], "alpha")
        self.assertIn(("draft_pr", "feat/canopy-supervisor-alpha", "main"),
                      self.git.calls)

    def test_interrupted_worker_local_evidence_recovers_without_retry(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        worktree = Path(self._get("alpha")["worktree"])
        source = worker.worker_evidence_path(worktree)
        source.write_text(json.dumps({
            "task_id": "alpha", "branch": "feat/canopy-supervisor-alpha",
            "commit_sha": "PENDING",
            "tests": [{"command": "test", "result": "PASS",
                       "output_excerpt": "OK"}],
            "changed_files": ["docs/alpha.md"], "draft": True,
        }), encoding="utf-8")
        self._mutate("alpha", status="interrupted", owner=None, pid=None)
        data = self.store.load()
        self.assertEqual(self.supervisor.recover(data), 1)
        self.assertEqual(data["tasks"][0]["status"], "verifying")
        self.assertFalse(source.exists())
        self.supervisor.verify(data)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "awaiting_review")
        self.assertEqual(self._get("alpha")["attempts"], 1)

    def test_rejects_mismatched_worker_evidence_without_trusting_it(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        task = self._get("alpha")
        source = worker.worker_evidence_path(Path(task["worktree"]))
        source.write_text(json.dumps({
            "task_id": "different", "branch": task["branch"],
            "tests": [], "draft": True,
        }), encoding="utf-8")
        self.assertFalse(self.supervisor._collect_worker_evidence(task))
        self.assertTrue(source.exists(), "preserve rejected report for diagnosis")
        self.assertFalse(worker.evidence_path(self.root, "alpha").exists())

    def test_rejects_oversized_worker_evidence(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        task = self._get("alpha")
        source = worker.worker_evidence_path(Path(task["worktree"]))
        source.write_bytes(b"x" * 131073)
        self.assertFalse(self.supervisor._collect_worker_evidence(task))
        self.assertFalse(worker.evidence_path(self.root, "alpha").exists())

    def test_recovery_requeues_expired_lease_with_checkpoint(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._mutate("alpha", lease_expires_at=0.0, pid=777)
        self.git.alive.add(777)
        data = self.store.load()
        self.assertEqual(self.supervisor.recover(data), 1)
        self.store.save(data)
        recovered = self._get("alpha")
        self.assertEqual(recovered["status"], "queued")
        self.assertEqual(recovered["checkpoint"]["stage"], "recovered")
        self.assertIn(("terminate", 777), self.git.calls)

    def test_recovery_replays_interrupted_checkpoint(self):
        self._add(task_definition("alpha"))
        self._mutate("alpha", status="interrupted", attempts=1, pid=None,
                     lease_expires_at=0.0, checkpoint={"stage": "clean-shutdown"})
        data = self.store.load()
        self.assertEqual(self.supervisor.recover(data), 1)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "queued")
        self.assertEqual(self._get("alpha")["checkpoint"]["stage"], "recovered")

    def test_recovery_uses_existing_evidence_after_restart(self):
        self._add(task_definition("alpha"))
        self._write_evidence("alpha")
        self._mutate("alpha", status="interrupted", attempts=1, pid=None,
                     lease_expires_at=0.0)
        data = self.store.load()
        self.supervisor.recover(data)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "verifying")
        self.assertEqual(self._get("alpha")["checkpoint"]["stage"], "recovered-evidence")

    def test_recovery_blocks_after_attempt_limit(self):
        self._add(task_definition("alpha"))
        self._mutate("alpha", status="running", attempts=2, lease_expires_at=0.0, pid=0)
        data = self.store.load()
        self.supervisor.recover(data)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "blocked")

    def test_stalled_worker_is_interrupted_and_requeued(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        task = self._get("alpha")
        signature = list(worker.progress_signature(
            Path(task["worktree"]), self.root / "logs" / "alpha.log"))
        self._mutate("alpha", last_progress_at=0.0, progress_signature=signature,
                     started_at=0.0)
        data = self.store.load()
        self.supervisor.monitor(data)
        self.store.save(data)
        interrupted = self._get("alpha")
        self.assertEqual(interrupted["status"], "queued")
        self.assertEqual(interrupted["checkpoint"]["stage"], "interrupted")

    def test_orphan_exit_with_evidence_is_verified_not_discarded(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha")
        data = self.store.load()
        self.supervisor.recover(data)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "running")
        self.supervisor.monitor(data)
        self.store.save(data)
        self.assertEqual(self._get("alpha")["status"], "verifying")

    def test_publish_creates_draft_pr_without_merge(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        task = self._get("alpha")
        self._write_evidence("alpha")
        self._mutate("alpha", status="verifying")
        self.supervisor.verify(self.store.load())
        task = self._get("alpha")
        published = self._get("alpha")
        self.assertEqual(published["status"], "awaiting_review")
        self.assertEqual(published["pr"]["number"], "55")
        self.assertEqual(published["evidence"]["commit_sha"], "c" * 40)
        self.assertIn(("draft_pr", task["branch"], "main"), self.git.calls)
        self.assertIn(("push", task["branch"], "origin"), self.git.calls)
        self.assertFalse(any("merge" in str(call).lower() for call in self.git.calls))

    def test_uncommitted_out_of_scope_file_blocks_publish_before_commit(self):
        self._add(task_definition("alpha"))
        self.git.pending = ["docs/alpha.md", "canopy/assets/icon.png"]
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha")
        self._mutate("alpha", status="verifying")
        self.supervisor.verify(self.store.load())
        failed = self._get("alpha")
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(any(call[0] == "commit_all" for call in self.git.calls))
        self.assertFalse(any(call[0] == "draft_pr" for call in self.git.calls))

    def test_publish_failure_is_checkpointed_without_pr(self):
        self._add(task_definition("alpha"))
        self.git.changed = ["canopy/assets/protected.png"]
        self.supervisor.dispatch(self.store.load())
        task = self._get("alpha")
        self._write_evidence("alpha")
        self._mutate("alpha", status="verifying")
        self.supervisor.verify(self.store.load())
        failed = self._get("alpha")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["checkpoint"]["stage"], "verification-error")
        self.assertFalse(any(call[0] == "draft_pr" for call in self.git.calls))

    def test_shutdown_checkpoints_active_tasks(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self.supervisor.shutdown()
        task = self._get("alpha")
        self.assertEqual(task["status"], "interrupted")
        self.assertEqual(task["checkpoint"]["stage"], "clean-shutdown")

    def test_failed_task_respects_backoff_before_redispatch(self):
        self._add(task_definition("alpha"))
        self._mutate("alpha", status="failed", attempts=1,
                     next_attempt_at=self.supervisor.now() + 60)
        data = self.store.load()
        self.assertFalse(self.supervisor.assignable(data["tasks"][0], data["tasks"]))
        self.assertEqual(self.supervisor.backoff(1), 30.0)

    def test_blocked_evidence_never_counts_as_success_or_pr(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha", result="BLOCKED")
        self._mutate("alpha", status="verifying")
        self.supervisor.verify(self.store.load())
        blocked = self._get("alpha")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["checkpoint"]["stage"], "prerequisites-blocked")
        self.assertFalse(any(call[0] == "draft_pr" for call in self.git.calls))
        self.assertFalse(any(call[0] in ("commit_all", "push")
                             for call in self.git.calls),
                         "unverified BLOCKED edits must remain local")

    def test_not_run_evidence_blocks_campaign(self):
        self.assertEqual(self.supervisor._evidence_outcome(
            {"tests": [{"result": "NOT RUN"}]}), "blocked")

    def test_implementation_requires_verifiable_artifact(self):
        definition = task_definition("alpha")
        definition["kind"] = "implementation"
        definition["artifacts"] = [{"path": "build/app", "sha256": "a" * 64}]
        clean = policy.validate_task(definition)
        self._add(clean)
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha", extra={"artifacts": [
            {"path": "build/app", "sha256": "a" * 64}]})
        self._mutate("alpha", status="verifying")
        self.supervisor.verify(self.store.load())
        self.assertEqual(self._get("alpha")["status"], "failed")
        self.assertFalse(any(call[0] == "draft_pr" for call in self.git.calls))

    def test_existing_open_pr_is_reused_without_duplicate(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha")
        self._mutate("alpha", status="verifying")
        self.git.find_open_pr = lambda *a, **k: self.git.pr_url
        self.supervisor.verify(self.store.load())
        self.assertEqual(self._get("alpha")["pr"]["number"], "55")
        self.assertFalse(any(call[0] == "draft_pr" for call in self.git.calls))

    def test_no_diff_task_finishes_without_draft_pr(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha")
        self.git.pending = []
        self._mutate("alpha", status="verifying")
        self.supervisor.verify(self.store.load())
        self.assertEqual(self._get("alpha")["status"], "done")
        self.assertFalse(any(call[0] == "draft_pr" for call in self.git.calls))

    def test_dashboard_reports_workers_prs_and_next_actions(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        data = self.store.load()
        data["tasks"][0]["pr"] = {"number": 7, "url": "x", "draft": True}
        self.store.save(data)
        text = self.store.dashboard(data, self.config)
        for section in ("## Active workers", "## Completed tasks and PRs", "## Next actions"):
            self.assertIn(section, text)
        self.assertIn("PR #7", text)

    def test_step_auto_queues_successive_unattended_cycles(self):
        items = [task_definition(f"wave-{index}") for index in range(6)]

        def select(existing, max_workers, *args, **kwargs):
            ids = {task["id"] for task in existing}
            active = sum(task["status"] not in roadmap.TERMINAL for task in existing)
            return [item for item in items if item["id"] not in ids][:max(0, max_workers - active)]

        with patch.object(roadmap, "select", side_effect=select):
            for wave in range(3):
                self.supervisor.step()
                data = self.store.load()
                expected = 2 * (wave + 1)
                self.assertEqual(len(data["tasks"]), expected)
                for task in data["tasks"]:
                    task["status"] = "awaiting_review"
                self.store.save(data)
        events = [json.loads(line)["event"]
                  for line in self.store.history_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events.count("auto_queued"), 6)
        self.assertEqual(len({task["id"] for task in self.store.load()["tasks"]}), 6)

    def test_step_monitors_running_workers(self):
        self._add(task_definition("alpha"))
        self.supervisor.dispatch(self.store.load())
        self._write_evidence("alpha")
        self.supervisor.step()
        self.assertEqual(self._get("alpha")["status"], "awaiting_review")
        self.assertEqual(self._get("alpha")["pr"]["number"], "55")

    def test_step_writes_dashboard(self):
        self._add(task_definition("alpha"))
        self.supervisor.step()
        self.assertTrue(self.store.dashboard_path.is_file())
        self.assertIn("alpha", self.store.dashboard_path.read_text(encoding="utf-8"))

    def test_run_releases_lock_between_steps(self):
        observed = []

        def wait_between_steps(interval):
            try:
                with state.exclusive_lock(self.store.lock_path):
                    observed.append("free")
            except state.LockBusy:
                observed.append("busy")
            self.supervisor.stop()

        self.supervisor._stop.wait = wait_between_steps
        self.supervisor.run(interval=0)
        self.assertEqual(observed, ["free"])

    def test_stop_file_requests_clean_shutdown(self):
        self._add(task_definition("alpha"))

        real_step = self.supervisor.step

        def trigger():
            real_step()
            state.atomic_write(self.store.stop_path, "stop\n")

        with patch.object(self.supervisor, "step", side_effect=trigger):
            self.supervisor.run(interval=0)
        self.assertFalse(self.store.stop_path.exists())
        self.assertEqual(self._get("alpha")["status"], "interrupted")
        self.assertEqual(self._get("alpha")["checkpoint"]["stage"], "clean-shutdown")

    def test_one_shot_run_does_not_kill_live_workers(self):
        self._add(task_definition("alpha"))
        data = self.supervisor.run(once=True)
        self.assertEqual(data["tasks"][0]["status"], "running")
        self.assertFalse(any(call[0] == "terminate" for call in self.git.calls))


class CliTests(unittest.TestCase):
    def test_init_add_check_status_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            (repo / ".git").mkdir(parents=True)
            root = base / "state"
            common = ["--state-root", str(root)]
            self.assertEqual(cli_main(common + ["init", "--repo", str(repo)]), 0)
            args = common + ["add-task", "--id", "alpha", "--title", "Doc task",
                             "--objective", "Write a bounded documentation file for the queue.",
                             "--scope", "docs/alpha.md"]
            self.assertEqual(cli_main(args), 0)
            self.assertEqual(cli_main(common + ["add-task", "--id", "alpha", "--title", "Dup",
                                                "--objective", "Duplicate id must be refused.",
                                                "--scope", "docs/alpha.md"]), 2)
            self.assertEqual(cli_main(common + ["check"]), 0)
            self.assertEqual(cli_main(common + ["status"]), 0)
            self.assertEqual(cli_main(common + ["pause"]), 0)
            self.assertTrue((root / "PAUSED").exists())
            self.assertEqual(cli_main(common + ["resume"]), 0)
            self.assertFalse((root / "PAUSED").exists())

    def test_cli_retry_permission_rejection_preserves_worktree_and_requeues(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            (repo / ".git").mkdir(parents=True)
            root = base / "state"
            common = ["--state-root", str(root)]
            self.assertEqual(cli_main(common + ["init", "--repo", str(repo)]), 0)
            store = state.TaskStore(root)
            worktree = root / "worktrees" / "alpha"
            worktree.mkdir(parents=True)
            changed = worktree / "docs" / "alpha.md"
            changed.parent.mkdir()
            changed.write_text("valuable existing code\n", encoding="utf-8")
            task = state.new_task(task_definition("alpha"), 2)
            task.update({"status": "blocked", "attempts": 2, "worktree": str(worktree),
                         "owner": None, "pid": None})
            data = store.load()
            data["tasks"].append(task)
            store.save(data)
            (root / "logs").mkdir(exist_ok=True)
            (root / "logs" / "alpha.log").write_text(
                "permission requested: external_directory ... auto-rejecting\n",
                encoding="utf-8")
            retry = common + ["retry-evidence-permission", "--id", "alpha"]
            self.assertEqual(cli_main(retry), 2, "repair must require paused state")
            self.assertEqual(cli_main(common + ["pause"]), 0)
            self.assertEqual(cli_main(retry), 0)
            updated = store.load()["tasks"][0]
            self.assertEqual(updated["status"], "queued")
            self.assertEqual(updated["attempts"], 0)
            self.assertEqual(updated["worktree"], str(worktree))
            self.assertEqual(changed.read_text(), "valuable existing code\n")

    def test_cli_retry_permission_rejects_unproven_or_live_work(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            (repo / ".git").mkdir(parents=True)
            root = base / "state"
            common = ["--state-root", str(root)]
            self.assertEqual(cli_main(common + ["init", "--repo", str(repo)]), 0)
            store = state.TaskStore(root)
            task = state.new_task(task_definition("alpha"), 2)
            task.update({"status": "blocked", "attempts": 2})
            data = store.load()
            data["tasks"].append(task)
            store.save(data)
            self.assertEqual(cli_main(common + ["pause"]), 0)
            retry = common + ["retry-evidence-permission", "--id", "alpha"]
            self.assertEqual(cli_main(retry), 2, "missing log cannot justify retry")
            (root / "logs").mkdir(exist_ok=True)
            log = root / "logs" / "alpha.log"
            log.write_text("some other error", encoding="utf-8")
            self.assertEqual(cli_main(retry), 2, "unrelated failure cannot justify retry")
            log.write_text("external_directory: auto-rejecting", encoding="utf-8")
            data = store.load()
            data["tasks"][0]["status"] = "running"
            store.save(data)
            self.assertEqual(cli_main(retry), 2, "live task cannot be requeued")
            data["tasks"][0]["status"] = "blocked"
            data["tasks"][0]["pr"] = {"number": "88"}
            store.save(data)
            self.assertEqual(cli_main(retry), 2, "published PR cannot be requeued")

    def test_cli_reverify_cache_failure_reuses_evidence_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            state_root = base / "state"
            common = ["--state-root", str(state_root)]
            self.assertEqual(cli_main(common + ["init", "--repo", str(repo)]), 0)
            store = state.TaskStore(state_root)
            worktree = base / "worker"
            worktree.mkdir()
            gitops.run(["git", "init"], cwd=worktree)
            gitops.run(["git", "checkout", "-b", "feat/canopy-supervisor-alpha"],
                       cwd=worktree)
            gitops.run(["git", "-c", "user.name=Test", "-c", "user.email=t@t",
                        "commit", "--allow-empty", "-m", "init"], cwd=worktree)
            file = worktree / "docs" / "alpha.md"
            file.parent.mkdir()
            file.write_text("verified work\n", encoding="utf-8")
            generated = worktree / "canopy_core" / "__pycache__" / "__init__.cpython-314.pyc"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"bytecode residue")
            task = state.new_task(task_definition("alpha"), 2)
            task.update({
                "status": "failed", "attempts": 1, "pid": None,
                "worktree": str(worktree),
                "last_error": "verification failed: PolicyError: changed file outside task scope: "
                              "canopy_core/__pycache__/__init__.cpython-314.pyc",
                "checkpoint": {"stage": "verification-error"},
            })
            data = store.load()
            data["tasks"].append(task)
            store.save(data)
            evidence = worker.evidence_path(state_root, "alpha")
            evidence.parent.mkdir(parents=True)
            evidence.write_text(json.dumps({
                "task_id": "alpha", "branch": "feat/canopy-supervisor-alpha",
                "commit_sha": "PENDING", "draft": True,
                "tests": [{"command": "python -m unittest",
                           "result": "PASS", "output_excerpt": "OK"}],
                "changed_files": ["docs/alpha.md"],
            }), encoding="utf-8")
            cmd = common + ["retry-verification", "--id", "alpha"]
            self.assertEqual(cli_main(cmd), 2, "must pause before re-verification")
            self.assertEqual(cli_main(common + ["pause"]), 0)
            self.assertEqual(cli_main(cmd), 0)
            replay = store.load()["tasks"][0]
            self.assertEqual(replay["status"], "verifying")
            self.assertEqual(replay["attempts"], 1, "must not charge another model attempt")
            self.assertTrue(evidence.is_file())
            self.assertEqual(file.read_text(encoding="utf-8"), "verified work\n")
            self.assertTrue(generated.is_file())
            self.assertEqual(cli_main(cmd), 2, "cannot requeue active verification twice")

    def test_cli_reverify_rejects_unrelated_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            (repo / ".git").mkdir(parents=True)
            state_root = base / "state"
            common = ["--state-root", str(state_root)]
            self.assertEqual(cli_main(common + ["init", "--repo", str(repo)]), 0)
            store = state.TaskStore(state_root)
            task = state.new_task(task_definition("alpha"), 2)
            task.update({"status": "failed", "attempts": 1, "pid": None,
                         "checkpoint": {"stage": "verification-error"},
                         "last_error": "verification failed: PolicyError: changed file "
                                       "outside task scope: canopy/assets/art.png"})
            data = store.load()
            data["tasks"].append(task)
            store.save(data)
            self.assertEqual(cli_main(common + ["pause"]), 0)
            self.assertEqual(cli_main(
                common + ["retry-verification", "--id", "alpha"]), 2)
            self.assertEqual(store.load()["tasks"][0]["attempts"], 1)

    def test_cli_feed_enqueues_from_roadmap(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            (repo / ".git").mkdir(parents=True)
            root = base / "state"
            common = ["--state-root", str(root)]
            cli_main(common + ["init", "--repo", str(repo)])
            with patch.object(roadmap, "select", return_value=[task_definition("auto")]):
                self.assertEqual(cli_main(common + ["feed"]), 0)
            tasks = state.TaskStore(root).load()["tasks"]
            self.assertEqual([task["id"] for task in tasks], ["auto"])

    def test_cli_rejects_protected_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            (repo / ".git").mkdir(parents=True)
            root = base / "state"
            cli_main(["--state-root", str(root), "init", "--repo", str(repo)])
            code = cli_main([
                "--state-root", str(root), "add-task", "--id", "bad", "--title", "Bad scope",
                "--objective", "Attempt to edit approved artwork without approval.",
                "--scope", "canopy/assets/icon.png",
            ])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
