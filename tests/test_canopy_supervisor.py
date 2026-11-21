"""Safety and correctness tests for the Canopy multi-agent supervisor."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from canopy_supervisor import credentials, gitops, policy, state, worker
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
        with patch.object(gitops, "status_porcelain", return_value=[" M docs/a.md"]), \
                patch.object(gitops, "run", side_effect=lambda args, **kw: calls.append(args) or
                             ("a" * 40 if args[-1] == "HEAD" else "")):
            sha = gitops.commit_all(Path("."), "test commit")
        self.assertEqual(sha, "a" * 40)
        self.assertIn(["git", "add", "-A"], calls)
        self.assertTrue(any("user.name=Canopy Supervisor" in arg for call in calls for arg in call))

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

    def _write_evidence(self, task_id, commit="PENDING"):
        directory = self.root / "evidence" / task_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "evidence.json").write_text(json.dumps({
            "task_id": task_id, "branch": f"feat/canopy-supervisor-{task_id}",
            "commit_sha": commit,
            "tests": [{"command": "python -m unittest tests.test_x", "result": "PASS",
                       "output_excerpt": "OK"}],
            "changed_files": [f"docs/{task_id}.md"], "draft": True,
            "notes": "bounded task",
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
