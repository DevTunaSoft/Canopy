"""Offline unit tests for the shell single-instance lock and takeover policy.

No real desktop, Qt runtime, Linux Mint session or background service is used.
PID liveness is injected as a deterministic callable. One test exercises the
real default probe against this test process on the current host only.
"""

import os
import tempfile
import unittest

from canopy_features.reliability.single_instance_guard import (
    ACQUIRED,
    ALREADY_OWNED,
    COMPETING_INSTANCE,
    INVALID_LOCK,
    LIVE_TAKEN_OVER,
    MAX_LOCK_BYTES,
    STALE_LOCK_BLOCKED,
    STALE_TAKEN_OVER,
    LockRecord,
    SingleInstanceGuard,
    TakeoverPolicy,
    pid_is_alive,
)


class SingleInstanceGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-sig-test-")
        self.addCleanup(temporary.cleanup)
        self.dir = temporary.name
        self.path = os.path.join(self.dir, "shell.lock")
        self.probe_calls = []

    def guard(self, alive=None):
        def probe(pid):
            self.probe_calls.append(pid)
            return bool(alive) if alive is not None else False
        return SingleInstanceGuard(self.path, probe=probe)

    def seed(self, pid, owner="old-shell"):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(LockRecord(pid=pid, owner=owner).to_text())

    def raw(self):
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.read()

    # Acquisition ---------------------------------------------------------

    def test_first_acquire_claims_lock_without_probing(self):
        guard = self.guard()
        decision = guard.acquire(pid=2001, owner="classic-shell")
        self.assertEqual(decision.status, ACQUIRED)
        self.assertTrue(decision.granted)
        self.assertEqual(decision.pid, 2001)
        self.assertIsNone(decision.previous_pid)
        self.assertEqual(self.probe_calls, [])
        self.assertEqual(LockRecord.parse(self.raw()),
                         LockRecord(pid=2001, owner="classic-shell"))

    def test_own_pid_is_already_owned_noop(self):
        self.seed(2002)
        guard = self.guard(alive=True)
        decision = guard.acquire(pid=2002)
        self.assertEqual(decision.status, ALREADY_OWNED)
        self.assertTrue(decision.granted)
        self.assertEqual(self.probe_calls, [])
        self.assertIn('"pid": 2002', self.raw())

    # Competing instance ---------------------------------------------------

    def test_competing_live_instance_is_refused(self):
        self.seed(3001, owner="other-shell")
        guard = self.guard(alive=True)
        before = self.raw()
        decision = guard.acquire(pid=4001, owner="classic-shell")
        self.assertEqual(decision.status, COMPETING_INSTANCE)
        self.assertFalse(decision.granted)
        self.assertEqual(decision.previous_pid, 3001)
        self.assertEqual(self.probe_calls, [3001])
        self.assertEqual(self.raw(), before)
        self.assertIn("another live process", decision.reason)

    def test_competing_instance_survives_stale_only_default(self):
        self.seed(3002)
        decision = self.guard(alive=True).acquire(pid=4002)
        self.assertFalse(decision.granted)
        self.assertEqual(decision.status, COMPETING_INSTANCE)

    def test_explicit_always_policy_takes_over_live_owner(self):
        self.seed(3003)
        guarded = self.guard(alive=True)
        decision = guarded.acquire(pid=4003,
                                   policy=TakeoverPolicy.ALWAYS)
        self.assertEqual(decision.status, LIVE_TAKEN_OVER)
        self.assertTrue(decision.granted)
        self.assertEqual(decision.previous_pid, 3003)
        self.assertEqual(LockRecord.parse(self.raw()).pid, 4003)

    # Stale PID ------------------------------------------------------------

    def test_stale_pid_is_taken_over(self):
        self.seed(5001, owner="crashed-shell")
        guard = self.guard(alive=False)
        decision = guard.acquire(pid=6001, owner="classic-shell")
        self.assertEqual(decision.status, STALE_TAKEN_OVER)
        self.assertTrue(decision.granted)
        self.assertEqual(decision.previous_pid, 5001)
        self.assertEqual(self.probe_calls, [5001])
        self.assertEqual(LockRecord.parse(self.raw()),
                         LockRecord(pid=6001, owner="classic-shell"))

    def test_policy_never_blocks_stale_takeover(self):
        self.seed(5002)
        before = self.raw()
        guard = self.guard(alive=False)
        decision = guard.acquire(pid=6002, policy=TakeoverPolicy.NEVER)
        self.assertEqual(decision.status, STALE_LOCK_BLOCKED)
        self.assertFalse(decision.granted)
        self.assertEqual(self.raw(), before)

    # Invalid / bounded input ----------------------------------------------

    def test_malformed_lock_is_refused_without_overwrite(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        guard = self.guard()
        decision = guard.acquire(pid=7001)
        self.assertEqual(decision.status, INVALID_LOCK)
        self.assertFalse(decision.granted)
        self.assertEqual(self.probe_calls, [])
        self.assertEqual(self.raw(), "{not json")

    def test_oversized_lock_is_invalid_bounded_read(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("x" * (MAX_LOCK_BYTES + 1))
        self.assertEqual(self.guard().read()[0], "INVALID")
        decision = self.guard().acquire(pid=7002)
        self.assertEqual(decision.status, INVALID_LOCK)
        self.assertEqual(os.path.getsize(self.path), MAX_LOCK_BYTES + 1)

    def test_explicit_always_can_replace_malformed_lock(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("garbage")
        decision = self.guard().acquire(pid=7003,
                                        policy=TakeoverPolicy.ALWAYS)
        self.assertEqual(decision.status, STALE_TAKEN_OVER)
        self.assertEqual(LockRecord.parse(self.raw()).pid, 7003)

    def test_invalid_pid_and_policy_rejected(self):
        guard = self.guard()
        with self.assertRaises(ValueError):
            guard.acquire(pid=0)
        with self.assertRaises(TypeError):
            guard.acquire(pid="123")
        with self.assertRaises(TypeError):
            guard.acquire(policy="always")
        with self.assertRaises(ValueError):
            guard.acquire(owner="")

    # Release --------------------------------------------------------------

    def test_release_removes_only_own_lock(self):
        self.seed(8001)
        guard = self.guard()
        self.assertFalse(guard.release(pid=9001))
        self.assertIn('"pid": 8001', self.raw())
        self.assertTrue(guard.release(pid=8001))
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(guard.release(pid=8001))

    def test_release_ignores_invalid_lock(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("broken")
        self.assertFalse(self.guard().release(pid=8002))
        self.assertTrue(os.path.exists(self.path))

    # Real default probe on this host only --------------------------------

    def test_default_probe_finds_current_process_on_this_host(self):
        current = os.getpid()
        self.assertTrue(pid_is_alive(current))
        self.assertFalse(pid_is_alive(0))
        self.assertFalse(pid_is_alive(-5))


if __name__ == "__main__":
    unittest.main()
