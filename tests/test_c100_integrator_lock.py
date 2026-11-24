"""Regression tests for the atomic stale-safe integrator lock."""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.qa.integrator_lock import (  # noqa: E402  # type: ignore[import-not-found]
    LockHeld, acquire, clear_stale_lock, lock_state, process_alive,
    process_start_time, read_lock,
)


class IntegratorLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "integrator.lock"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_normal_acquire_touch_release(self) -> None:
        with acquire(self.path, owner="test") as handle:
            state = lock_state(self.path)
            self.assertEqual(state.status, "live")
            self.assertEqual(state.info["owner"], "test")
            first = read_lock(self.path)["ts"]
            time.sleep(0.01)
            handle.touch()
            self.assertGreater(read_lock(self.path)["ts"], first)
        self.assertFalse(self.path.exists())

    def test_active_lock_blocks_second_acquirer(self) -> None:
        with acquire(self.path, owner="owner-1"):
            with self.assertRaises(LockHeld):
                acquire(self.path, owner="owner-2", attempts=1)

    def test_stale_dead_pid_is_cleared_and_reacquired(self) -> None:
        self.path.write_text(json.dumps({
            "pid": 999_999_999, "start": 1.0, "token": "dead",
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }))
        state = lock_state(self.path)
        self.assertEqual(state.status, "stale")
        self.assertEqual(state.reason, "owner_dead_or_pid_reused")
        cleared, reason = clear_stale_lock(self.path)
        self.assertTrue(cleared)
        self.assertIn("cleared_", reason)
        with acquire(self.path) as handle:
            self.assertEqual(lock_state(self.path).status, "live")
            self.assertEqual(handle.token, read_lock(self.path)["token"])

    def test_legacy_and_malformed_locks_are_recoverable(self) -> None:
        for payload in ("12345", "not json", "{", '[]'):
            with self.subTest(payload=payload):
                self.path.write_text(payload, encoding="utf-8")
                info = read_lock(self.path)
                self.assertTrue(info.get("legacy") or info.get("malformed"))
                cleared, _ = clear_stale_lock(self.path)
                self.assertTrue(cleared)
                self.assertFalse(self.path.exists())

    def test_legacy_lock_with_live_pid_is_not_cleared(self) -> None:
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        state = lock_state(self.path)
        self.assertEqual(state.status, "live")
        self.assertEqual(state.reason, "legacy_live_owner")
        cleared, reason = clear_stale_lock(self.path)
        self.assertFalse(cleared)
        self.assertEqual(reason, "live")

    def test_pid_reuse_guard(self) -> None:
        self.path.write_text(json.dumps({
            "pid": os.getpid(), "start": 1.0, "token": "reuse",
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }))
        state = lock_state(self.path)
        self.assertEqual(state.status, "stale")
        self.assertEqual(state.reason, "owner_dead_or_pid_reused")
        cleared, _ = clear_stale_lock(self.path)
        self.assertTrue(cleared)

    def test_live_process_with_stale_heartbeat_is_not_unlocked(self) -> None:
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(seconds=10_000)).isoformat()
        self.path.write_text(json.dumps({
            "pid": os.getpid(), "start": process_start_time(os.getpid()),
            "token": "hung", "ts": old,
        }))
        state = lock_state(self.path)
        self.assertEqual(state.status, "stale")
        self.assertEqual(state.reason, "heartbeat_stale_but_process_alive")
        cleared, reason = clear_stale_lock(self.path)
        self.assertFalse(cleared)
        self.assertEqual(reason, state.reason)
        with self.assertRaises(LockHeld):
            acquire(self.path, attempts=1)

    def test_release_and_touch_verify_token(self) -> None:
        with acquire(self.path) as handle:
            self.path.write_text(json.dumps({
                "pid": 999_999_999, "start": 1.0, "token": "other",
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }))
            with self.assertRaises(LockHeld):
                handle.touch()
            handle.release()
            self.assertTrue(self.path.exists())

    def test_simultaneous_acquisition_has_single_winner(self) -> None:
        barrier = threading.Barrier(6)
        results: list[str] = []

        def worker() -> None:
            barrier.wait()
            try:
                handle = acquire(self.path, attempts=1)
            except LockHeld:
                results.append("lost")
            else:
                results.append("won")
                time.sleep(0.05)
                handle.release()

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(results.count("won"), 1)
        self.assertEqual(results.count("lost"), 5)
        self.assertFalse(self.path.exists())

    def test_unexpected_termination_and_restart_recovery(self) -> None:
        child = (
            "import json,os,pathlib,sys;"
            "sys.path.insert(0,%r);"
            "from tools.qa.integrator_lock import acquire;"
            "acquire(pathlib.Path(%r));"
            "os._exit(0)" % (str(ROOT), str(self.path))
        )
        result = subprocess.run([sys.executable, "-c", child],
                                capture_output=True, text=True, timeout=30,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = lock_state(self.path)
        self.assertEqual(state.status, "stale")
        self.assertEqual(state.reason, "owner_dead_or_pid_reused")
        cleared, _ = clear_stale_lock(self.path)
        self.assertTrue(cleared)
        with acquire(self.path) as handle:
            self.assertEqual(handle.info["owner"], "integrator")
            self.assertEqual(lock_state(self.path).status, "live")

    def test_process_alive_rejects_dead_pid(self) -> None:
        self.assertFalse(process_alive(999_999_999))
        self.assertTrue(process_alive(os.getpid(), process_start_time(os.getpid())))


if __name__ == "__main__":
    unittest.main()
