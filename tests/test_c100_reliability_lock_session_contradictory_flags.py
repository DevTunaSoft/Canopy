"""RED regression: a fail-closed SessionState must not claim suspended-but-unlocked.

``SessionState`` is the canonical, fail-closed state published to host-facing
snapshots. Its own contract says SUSPEND forces the locked flag on and an
UNLOCK while suspended cannot expose an unlocked session, so the flag pair
(suspended=True, locked=False) is contradictory. On the pinned base the public
frozen dataclass accepts that pair, and a caller-built state can be published
by the composition layer as a valid session view.

Pure in-memory units only: no D-Bus, suspend/resume hardware, Qt, QML or I/O.
"""
import unittest

from canopy_features.reliability import lock_session_events as lse
from canopy_features.reliability import session_lifecycle_snapshot as snapshot
from canopy_features.reliability import theme_transition_rollback as theme
from canopy_features.windows import focus_intents as focus


class ForgedReconciler(lse.Reconciler):
    """Caller-built reconciler whose public state is a forged SessionState."""

    def __init__(self, forged):
        super().__init__(initial_locked=False)
        self._state = forged


def _parts(forged):
    policy = focus.PermissionPolicy()
    return (ForgedReconciler(forged), theme.ThemeTransitionRollback(),
            focus.FocusBroker(policy.authorize), policy)


class ContradictorySessionFlagsTests(unittest.TestCase):
    def test_suspended_unlocked_state_is_refused(self):
        with self.assertRaises(lse.LockSessionEventError):
            lse.SessionState(True, False)

    def test_non_bool_flags_are_refused(self):
        for suspended, locked in ((1, False), (True, 1), (None, False)):
            with self.subTest(suspended=suspended, locked=locked):
                with self.assertRaises(lse.LockSessionEventError):
                    lse.SessionState(suspended, locked)

    def test_contradictory_flags_never_publish_a_session_view(self):
        # On the base tree compose() accepts the forged state and publishes
        # suspended=True with locked=False -- a false fail-closed claim.
        def attempt():
            forged = lse.SessionState(True, False)
            return snapshot.compose(*_parts(forged))

        with self.assertRaises(lse.LockSessionEventError):
            attempt()

    def test_reconciler_states_remain_consistent(self):
        r = lse.Reconciler(initial_locked=False)
        sequence = ((lse.LOCK, 1), (lse.SUSPEND, 2), (lse.UNLOCK, 3),
                    (lse.RESUME, 4), (lse.UNLOCK, 5))
        for kind, timestamp in sequence:
            outcome = r.observe(lse.SessionEvent(kind, timestamp, "logind"))
            self.assertFalse(outcome.state.suspended
                             and not outcome.state.locked)
        self.assertEqual(r.state, lse.SessionState(False, False))


if __name__ == "__main__":
    unittest.main()
