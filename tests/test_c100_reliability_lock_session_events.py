"""Offline unit tests for bounded suspend/lock/resume event reconciliation.

No real D-Bus, logind, suspend/resume, Linux Mint session or compiled Qt is
exercised here. All events are constructed in process.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.reliability.lock_session_events import (
    DEFERRED, DUPLICATE, REDUNDANT, STALE, TRANSITION, KINDS,
    LockSessionEventError, Reconciler, SessionEvent, SessionState,
)


def event(kind, timestamp, source="logind"):
    return SessionEvent(kind, timestamp, source)


class LockSessionEventTests(unittest.TestCase):
    def test_canonical_suspend_lock_resume_unlock_order(self):
        reconciler = Reconciler(initial_locked=False)
        lock = reconciler.observe(event("lock", 10))
        suspend = reconciler.observe(event("suspend", 20))
        resume = reconciler.observe(event("resume", 30))
        unlock = reconciler.observe(event("unlock", 40))

        self.assertEqual([o.status for o in (lock, suspend, resume, unlock)],
                         [TRANSITION] * 4)
        self.assertEqual([o.state.label for o in (lock, suspend, resume, unlock)],
                         ["locked", "suspended", "locked", "active"])
        self.assertEqual(lock.state, SessionState(False, True))
        self.assertEqual(suspend.state, SessionState(True, True))
        self.assertEqual(resume.state, SessionState(False, True))
        self.assertEqual(unlock.state, SessionState(False, False))
        self.assertEqual(reconciler.accepted, 4)
        self.assertEqual([o.state.label for o in reconciler.history],
                         ["locked", "suspended", "locked", "active"])

    def test_suspend_forces_locked_from_unlocked_start(self):
        reconciler = Reconciler(initial_locked=False)
        self.assertEqual(reconciler.state.label, "active")
        self.assertTrue(reconciler.observe(event("suspend", 1)).state.locked)
        self.assertEqual(reconciler.observe(event("resume", 2)).state.label,
                         "locked")
        self.assertEqual(reconciler.observe(event("unlock", 3)).state.label,
                         "active")

    def test_duplicate_unlock_is_ignored(self):
        reconciler = Reconciler(initial_locked=True)
        first = reconciler.observe(event("unlock", 5, "dbus"))
        duplicate = reconciler.observe(event("unlock", 5, "dbus"))
        later = reconciler.observe(event("unlock", 6, "policy"))

        self.assertEqual(first.status, TRANSITION)
        self.assertEqual(duplicate.status, DUPLICATE)
        self.assertEqual(later.status, REDUNDANT)
        self.assertFalse(duplicate.transitioned)
        self.assertFalse(later.transitioned)
        self.assertEqual(reconciler.accepted, 1)
        self.assertEqual(reconciler.state.label, "active")
        self.assertEqual(len(reconciler.history), 1)

    def test_backwards_timestamp_does_not_regress_state(self):
        reconciler = Reconciler(initial_locked=False)
        locked = reconciler.observe(event("lock", 100))
        stale_unlock = reconciler.observe(event("unlock", 90))
        stale_lock = reconciler.observe(event("lock", 95))
        fresh_unlock = reconciler.observe(event("unlock", 110))

        self.assertEqual(locked.status, TRANSITION)
        self.assertEqual(stale_unlock.status, STALE)
        self.assertEqual(stale_lock.status, STALE)
        self.assertEqual(fresh_unlock.status, TRANSITION)
        self.assertEqual(reconciler.state.label, "active")
        self.assertEqual(reconciler.accepted, 2)
        self.assertEqual([o.status for o in reconciler.history],
                         [TRANSITION, TRANSITION])

    def test_stale_resume_cannot_clear_a_newer_suspend(self):
        reconciler = Reconciler(initial_locked=True)
        reconciler.observe(event("suspend", 200))
        result = reconciler.observe(event("resume", 150, "old-source"))
        self.assertEqual(result.status, STALE)
        self.assertEqual(reconciler.state, SessionState(True, True))

    def test_unlock_while_suspended_is_deferred_fail_closed(self):
        reconciler = Reconciler(initial_locked=True)
        reconciler.observe(event("suspend", 1))
        deferred = reconciler.observe(event("unlock", 2))
        self.assertEqual(deferred.status, DEFERRED)
        self.assertEqual(reconciler.state, SessionState(True, True))
        self.assertEqual(reconciler.observe(event("resume", 3)).state.label,
                         "locked")
        self.assertEqual(reconciler.observe(event("unlock", 4)).state.label,
                         "active")

    def test_duplicate_after_first_source_is_still_idempotent(self):
        reconciler = Reconciler(initial_locked=False)
        reconciler.observe(event("lock", 7, "logind"))
        first = reconciler.observe(event("unlock", 8, "dbus"))
        duplicate = reconciler.observe(event("unlock", 8, "dbus"))
        self.assertEqual(first.status, TRANSITION)
        self.assertEqual(duplicate.status, DUPLICATE)
        self.assertEqual(reconciler.accepted, 2)

    def test_history_and_duplicate_cache_are_bounded(self):
        reconciler = Reconciler(initial_locked=False, duplicate_window=4,
                                history_limit=2)
        for i in range(200):
            kind = "lock" if i % 2 == 0 else "unlock"
            self.assertEqual(reconciler.observe(event(kind, i, "src")).status,
                             TRANSITION)
        self.assertEqual(reconciler.accepted, 200)
        self.assertEqual(len(reconciler.history), 2)
        # Private cache sizes are asserted to prove bounded memory, not speed.
        self.assertLessEqual(len(reconciler._seen), 4)
        self.assertLessEqual(len(reconciler._seen_set), 4)

    def test_invalid_events_rejected_without_state_change(self):
        reconciler = Reconciler(initial_locked=True)
        bad = (
            ("unknown kind", dict(kind="hibernate", timestamp=1)),
            ("nan timestamp", dict(kind="lock", timestamp=float("nan"))),
            ("inf timestamp", dict(kind="lock", timestamp=float("inf"))),
            ("bool timestamp", dict(kind="lock", timestamp=True)),
            ("huge timestamp", dict(kind="lock", timestamp=10 ** 20)),
            ("bad source", dict(kind="lock", timestamp=1, source="Bad Source")),
        )
        for label, kwargs in bad:
            with self.subTest(case=label):
                with self.assertRaises(LockSessionEventError):
                    SessionEvent(**kwargs)
        with self.assertRaises(LockSessionEventError):
            reconciler.observe("lock")
        self.assertEqual(reconciler.state.label, "locked")
        self.assertEqual(reconciler.accepted, 0)
        self.assertEqual(reconciler.history, ())

    def test_invalid_bounds_are_rejected(self):
        bad = (
            dict(initial_locked="yes"),
            dict(duplicate_window=0),
            dict(duplicate_window=1025),
            dict(history_limit=-1),
            dict(history_limit=1025),
        )
        for kwargs in bad:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(LockSessionEventError):
                    Reconciler(**kwargs)

    def test_outcomes_and_state_are_immutable(self):
        reconciler = Reconciler(initial_locked=False)
        outcome = reconciler.observe(event("lock", 1))
        for target, field in ((outcome, "status"), (outcome.state, "locked"),
                              (outcome.event, "kind")):
            with self.subTest(field=field):
                with self.assertRaises(FrozenInstanceError):
                    setattr(target, field, "changed")

    def test_kinds_are_exactly_the_four_power_and_lock_events(self):
        self.assertEqual(KINDS, frozenset({"suspend", "resume", "lock",
                                           "unlock"}))

    def test_module_has_no_polling_or_background_threads(self):
        source = (Path(__file__).resolve().parents[1] / "canopy_features"
                  / "reliability" / "lock_session_events.py").read_text()
        for token in ("sleep(", "import time", "Thread(", "QTimer",
                      "while True"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
