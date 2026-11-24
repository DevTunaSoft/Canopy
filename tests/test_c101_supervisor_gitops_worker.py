"""Contract tests for bounded supervisor worker PID handling.

Run: python -m unittest tests.test_c101_supervisor_gitops_worker -v
"""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
