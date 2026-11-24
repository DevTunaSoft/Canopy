"""Contract tests for bounded supervisor worker PID handling.

Run: python -m unittest tests.test_c101_supervisor_gitops_worker -v
"""
from contextlib import contextmanager, nullcontext
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import threading
import unittest

from canopy_supervisor import gitops
from canopy_supervisor.supervisor import Supervisor
from canopy_supervisor import worker
from canopy_supervisor.worker import WorkerLauncher


class FakeProcess:
    def __init__(self, pid, code=None):
        self.pid = pid
        self._code = code

    def poll(self):
        return self._code


@contextmanager
def launcher():
    with tempfile.TemporaryDirectory() as root:
        yield WorkerLauncher({}, Path(root), lambda: "test-token")


class WorkerPidTypeTests(unittest.TestCase):
    def test_wrong_type_pid_fails_closed(self):
        for bad in (None, 0, -1, True, "42", [], {}, 3.5):
            with self.subTest(pid=repr(bad)):
                with launcher() as worker:
                    self.assertIs(worker.knows(bad), False)
                    self.assertIsNone(worker.poll(bad))

    def test_known_pid_poll_and_release_still_work(self):
        with launcher() as worker:
            worker._processes[7] = FakeProcess(7, None)
            self.assertTrue(worker.knows(7))
            self.assertIsNone(worker.poll(7))
            self.assertTrue(worker.knows(7))
            worker._processes[7] = FakeProcess(7, 0)
            self.assertEqual(worker.poll(7), 0)
            self.assertFalse(worker.knows(7))

    def test_bool_pid_cannot_alias_integer_one(self):
        with launcher() as worker:
            worker._processes[1] = FakeProcess(1, 0)
            self.assertFalse(worker.knows(True))
            self.assertIsNone(worker.poll(True))
            self.assertEqual(worker.poll(1), 0)


class SupervisorBackoffTests(unittest.TestCase):
    def test_wrong_type_backoff_fails_closed_at_max_delay(self):
        for bad in (None, "3", True, 3.5, [], {}, -1, 0):
            with self.subTest(value=repr(bad)):
                self.assertEqual(Supervisor.backoff(bad), 300.0)

    def test_exponent_is_bounded(self):
        for attempts, expected in ((1, 30.0), (2, 60.0), (3, 120.0),
                                   (4, 240.0), (5, 300.0),
                                   (10 ** 6, 300.0)):
            with self.subTest(attempts=attempts):
                self.assertEqual(Supervisor.backoff(attempts), expected)


class GitOpsOutputBoundTests(unittest.TestCase):
    def test_oversized_command_output_fails_closed(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "x" * 2_000_000
        result.stderr = ""
        with patch("canopy_supervisor.gitops.subprocess.run",
                   return_value=result):
            with self.assertRaises(gitops.GitError):
                gitops.run(["git", "status"])

    def test_bounded_output_still_returned(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "ok\n"
        result.stderr = ""
        with patch("canopy_supervisor.gitops.subprocess.run",
                   return_value=result):
            self.assertEqual(gitops.run(["git", "status"]), "ok")


class FinishedProcess:
    next_pid = 100

    def __init__(self, *args, **kwargs):
        FinishedProcess.next_pid += 1
        self.pid = FinishedProcess.next_pid
        self.stopped = False

    def poll(self):
        return 0


class WorkerHandleCleanupTests(unittest.TestCase):
    def launcher(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        base = Path(root.name)
        worktree = base / "wt"
        worktree.mkdir()
        worker = WorkerLauncher(
            {"model": "opencode-go/x"}, base, lambda: "token",
            spawner=FinishedProcess)
        task = {"id": "t", "title": "x", "objective": "y",
                "scope": (), "branch": "b"}
        return worker, worktree, base / "log.txt", task

    def test_finished_handles_pruned_on_next_launch(self):
        worker, worktree, log, task = self.launcher()
        for _ in range(12):
            worker.launch(task, "worker-1", worktree, log)
        self.assertLessEqual(len(worker._processes), 1)

    def test_close_drops_all_launcher_handles(self):
        worker, worktree, log, task = self.launcher()
        worker.launch(task, "worker-1", worktree, log)
        self.assertEqual(len(worker._processes), 1)
        worker.close()
        self.assertEqual(worker._processes, {})


class LoopCleanupTests(unittest.TestCase):
    def test_once_loop_releases_launcher_handles(self):
        class CloseSpy:
            def __init__(self):
                self.closed = 0

            def close(self):
                self.closed += 1

        with tempfile.TemporaryDirectory() as d:
            store = MagicMock()
            store.stop_path = Path(d) / "stop"
            store.lock_path = Path(d) / "lock"
            sup = Supervisor.__new__(Supervisor)
            sup.config = {"poll_seconds": 0.001,
                          "model": "opencode-go/x"}
            sup.store = store
            launcher = CloseSpy()
            sup.launcher = launcher
            sup.git = MagicMock()
            sup.now = lambda: 0.0
            sup._stop = threading.Event()
            sup.step = lambda: {"tasks": []}
            sup.shutdown = MagicMock()
            with patch("canopy_supervisor.supervisor.state_module.exclusive_lock",
                       return_value=nullcontext()):
                sup._run_loop(once=True)
            self.assertEqual(launcher.closed, 1)
            self.assertFalse(sup.shutdown.called)


class WorkerRedactTests(unittest.TestCase):
    def test_wrong_type_input_is_redacted_not_raised(self):
        for bad in (None, 7, True, [], {}, b"raw-token"):
            with self.subTest(value=repr(bad)):
                out = worker.redact(bad)
                self.assertEqual(out, "[REDACTED]")
                self.assertNotIn("raw", out)

    def test_valid_text_still_redacted(self):
        self.assertEqual(worker.redact("plain text"), "plain text")
        self.assertEqual(worker.redact("\x1b[31msecret\x1b[0m"), "secret")


class GitOpsRunTypeTests(unittest.TestCase):
    def test_wrong_type_args_rejected_before_spawn(self):
        for bad in ("git status", None, 7, {}, b"git", ["git", 7]):
            with self.subTest(value=repr(bad)):
                with patch("canopy_supervisor.gitops.subprocess.run") as spawn:
                    with self.assertRaises(gitops.GitError):
                        gitops.run(bad)
                    spawn.assert_not_called()

    def test_valid_list_still_runs(self):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "ok\n"
        result.stderr = ""
        with patch("canopy_supervisor.gitops.subprocess.run",
                   return_value=result) as spawn:
            self.assertEqual(gitops.run(["git", "status"]), "ok")
        self.assertEqual(spawn.call_args.args[0], ["git", "status"])


class SupervisorAssignableTypeTests(unittest.TestCase):
    def supervisor(self):
        sup = Supervisor.__new__(Supervisor)
        sup.config = {"max_attempts": 3}
        sup.now = lambda: 100.0
        return sup

    def test_wrong_type_next_attempt_fails_closed(self):
        for bad in (None, [], {}, "soon", float("nan"),
                    float("inf"), -float("inf"), True):
            with self.subTest(value=repr(bad)):
                task = {"status": "queued", "next_attempt_at": bad}
                self.assertIs(self.supervisor().assignable(task, []), False)

    def test_valid_next_attempt_still_gates_scheduling(self):
        sup = self.supervisor()
        self.assertIs(sup.assignable(
            {"status": "queued", "next_attempt_at": 200}, []), False)
        self.assertIs(sup.assignable(
            {"status": "queued", "next_attempt_at": 50}, []), True)


if __name__ == "__main__":
    unittest.main()
