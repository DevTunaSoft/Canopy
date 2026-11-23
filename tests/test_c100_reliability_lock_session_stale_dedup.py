"""Regression tests: a rejected STALE observation leaves the dedup window unchanged.

The reconciler documents that a duplicate fingerprint is ignored and that a
stale event cannot regress committed state.  Registering a rejected event in
the bounded duplicate window can evict an accepted fingerprint, so replaying
that accepted event flips state instead of being ignored.  These tests pin the
transactional-integrity contract: rejection is a no-op on all reconciler state.
"""
import unittest

from canopy_features.reliability.lock_session_events import (
    DEFERRED, DUPLICATE, REDUNDANT, STALE, TRANSITION,
    Reconciler, SessionEvent, SessionState,
)


def event(kind, timestamp, source="x"):
    return SessionEvent(kind, timestamp, source)


class StaleDedupIntegrityTests(unittest.TestCase):
    def test_rejected_stale_does_not_evict_accepted_fingerprint(self):
        # Window of 2; one rejected stale event would evict suspend@100.
        r = Reconciler(initial_locked=True, duplicate_window=2, history_limit=8)
        self.assertEqual(r.observe(event("suspend", 100)).status, TRANSITION)
        self.assertEqual(r.observe(event("resume", 100)).status, TRANSITION)
        self.assertEqual(r.observe(event("lock", 50)).status, STALE)
        # The accepted fingerprint must still be recognised as a duplicate.
        replay = r.observe(event("suspend", 100))
        self.assertEqual(replay.status, DUPLICATE)
        self.assertFalse(replay.transitioned)
        self.assertEqual(r.state, SessionState(False, True))
        self.assertEqual(r.accepted, 2)
        self.assertEqual(len(r.history), 2)

    def test_rejected_stale_fingerprint_is_not_registered(self):
        r = Reconciler(initial_locked=True, duplicate_window=2, history_limit=8)
        self.assertEqual(r.observe(event("suspend", 100)).status, TRANSITION)
        before = set(r._seen)
        self.assertEqual(r.observe(event("lock", 50)).status, STALE)
        after = set(r._seen)
        # Dedup window is byte-for-byte unchanged by the rejection.
        self.assertEqual(after, before)
        self.assertNotIn(("lock", 50, "x"), r._seen_set)
        self.assertIn(("suspend", 100, "x"), r._seen_set)

    def test_repeated_stale_event_reports_stale_not_duplicate(self):
        # Since a stale event is never registered, repeating it is still stale.
        r = Reconciler(initial_locked=True, duplicate_window=4, history_limit=8)
        self.assertEqual(r.observe(event("suspend", 100)).status, TRANSITION)
        first = r.observe(event("unlock", 10))
        second = r.observe(event("unlock", 10))
        self.assertEqual(first.status, STALE)
        self.assertEqual(second.status, STALE)
        self.assertEqual(r.accepted, 1)
        self.assertEqual(r.state, SessionState(True, True))

    def test_default_window_stale_flood_cannot_evict_accepted(self):
        # At the default window of 64, 65 rejected events used to evict the
        # accepted fingerprint; its replay must still be DUPLICATE.
        r = Reconciler(initial_locked=True, history_limit=8)
        self.assertEqual(r.observe(event("suspend", 100)).status, TRANSITION)
        for i in range(65):
            self.assertEqual(r.observe(event("lock", 50 - i, "s%d" % i)).status,
                             STALE)
        replay = r.observe(event("suspend", 100))
        self.assertEqual(replay.status, DUPLICATE)
        self.assertEqual(r.accepted, 1)
        self.assertEqual(r.state, SessionState(True, True))

    def test_accepted_and_deferred_fingerprints_still_deduplicated(self):
        # Control: accepted and deferred observations remain registerable.
        r = Reconciler(initial_locked=True, duplicate_window=8, history_limit=8)
        self.assertEqual(r.observe(event("suspend", 1)).status, TRANSITION)
        self.assertEqual(r.observe(event("unlock", 2)).status, DEFERRED)
        self.assertEqual(r.observe(event("suspend", 1)).status, DUPLICATE)
        self.assertEqual(r.observe(event("unlock", 2)).status, DUPLICATE)
        self.assertEqual(r.observe(event("resume", 3)).status, TRANSITION)
        self.assertEqual(r.observe(event("resume", 3)).status, DUPLICATE)
        self.assertEqual(r.accepted, 2)

    def test_dedup_window_stays_bounded_under_mixed_events(self):
        # Control: rejecting stale events never grows the bounded window.
        window = 4
        r = Reconciler(initial_locked=False, duplicate_window=window,
                       history_limit=8)
        for i in range(50):
            r.observe(event("lock", i))
            r.observe(event("unlock", -i))  # stale, must not be remembered
        self.assertLessEqual(len(r._seen), window)
        self.assertLessEqual(len(r._seen_set), window)

    def test_stale_flood_cannot_flip_state_on_replay(self):
        # End-to-end: after a stale flood, replaying an accepted SUSPEND must
        # not force the locked flag back on through a spurious transition.
        r = Reconciler(initial_locked=False, duplicate_window=2, history_limit=8)
        self.assertEqual(r.observe(event("lock", 100)).status, TRANSITION)
        self.assertEqual(r.observe(event("unlock", 101)).status, TRANSITION)
        self.assertEqual(r.observe(event("lock", 50)).status, STALE)
        replay = r.observe(event("lock", 100))
        self.assertEqual(replay.status, DUPLICATE)
        self.assertEqual(r.state, SessionState(False, False))
        self.assertEqual(r.accepted, 2)


if __name__ == "__main__":
    unittest.main()
