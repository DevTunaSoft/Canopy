"""Regression tests for bounded integrator restart recovery."""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.qa.integrator_lock import (  # type: ignore[import-not-found]
    process_start_time,
)
from tools.qa.integrator_recovery import (  # type: ignore[import-not-found]
    recover, recovery_state_path,
)


class IntegratorRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.lock = base / "integrator.lock"
        self.log = pathlib.Path(os.devnull)
        self.daemon = base / "fake_daemon.py"
        self.marker = base / "started.txt"
        self.daemon.write_text(
            "from pathlib import Path\n"
            "Path(%r).write_text('started', encoding='utf-8')\n" % str(self.marker),
            encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_lock(self, *, pid: int, start: float | None, stale: bool = False) -> None:
        ts = datetime.datetime.now(datetime.timezone.utc)
        if stale:
            ts -= datetime.timedelta(seconds=10_000)
        self.lock.write_text(json.dumps({
            "pid": pid, "start": start, "token": "test",
            "ts": ts.isoformat(), "owner": "integrator",
        }), encoding="utf-8")

    def test_live_owner_is_never_restarted(self) -> None:
        self.write_lock(pid=__import__("os").getpid(), start=process_start_time(__import__("os").getpid()))
        result = recover(self.lock, self.daemon, self.log)
        self.assertEqual(result["action"], "keep")
        self.assertTrue(self.lock.exists())
        self.assertFalse(self.marker.exists())

    def test_live_owner_with_stale_heartbeat_alerts_only(self) -> None:
        self.write_lock(pid=__import__("os").getpid(),
                        start=process_start_time(__import__("os").getpid()),
                        stale=True)
        result = recover(self.lock, self.daemon, self.log)
        self.assertEqual(result["action"], "alert_only")
        self.assertEqual(result["reason"], "heartbeat_stale_but_process_alive")
        self.assertTrue(self.lock.exists())
        self.assertFalse(self.marker.exists())

    def test_dead_owner_clears_lock_and_starts_detached_daemon(self) -> None:
        self.write_lock(pid=999_999_999, start=1.0)
        result = recover(self.lock, self.daemon, self.log)
        self.assertEqual(result["action"], "restarted")
        self.assertTrue(result["lock_cleared"])
        self.assertIn("new_pid", result)
        deadline = time.time() + 10
        while time.time() < deadline and not self.marker.exists():
            time.sleep(0.05)
        self.assertTrue(self.marker.exists(), "detached replacement did not start")
        # Detached child inherits the log handle; let it exit before temp cleanup.
        time.sleep(0.5)
        state = json.loads(recovery_state_path(self.lock).read_text(encoding="utf-8"))
        self.assertEqual(state["attempts_in_window"], 1)

    def test_cooldown_prevents_repeated_restarts(self) -> None:
        self.write_lock(pid=999_999_999, start=1.0)
        first = recover(self.lock, self.daemon, self.log, launch=False)
        self.assertEqual(first["action"], "would_restart")
        self.write_lock(pid=999_999_999, start=1.0)
        second = recover(self.lock, self.daemon, self.log, launch=False)
        self.assertEqual(second["action"], "recovery_limit")
        self.assertEqual(second["reason"], "cooldown")

    def test_attempt_cap_with_expired_cooldown(self) -> None:
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(seconds=5000)).isoformat()
        recovery_state_path(self.lock).write_text(json.dumps({
            "last_attempt": old, "attempts_in_window": 2,
        }), encoding="utf-8")
        self.write_lock(pid=999_999_999, start=1.0)
        result = recover(self.lock, self.daemon, self.log, launch=False)
        self.assertEqual(result["action"], "recovery_limit")
        self.assertEqual(result["reason"], "max_attempts")

    def test_no_lock_returns_without_restart(self) -> None:
        result = recover(self.lock, self.daemon, self.log)
        self.assertEqual(result["lock_status"], "absent")
        self.assertEqual(result["action"], "none")


if __name__ == "__main__":
    unittest.main()
