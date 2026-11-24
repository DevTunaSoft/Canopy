"""Regression: theme state and candidate must not contradict each other.

The composed lifecycle record claims STATUS_OK only for an IDLE theme with a
single owner and no abandoned handles.  The theme ledger's invariant is that
IDLE means no in-flight candidate and PREPARED means exactly one.  A
hostile-but-bounded snapshot can claim IDLE while still carrying a candidate;
at b4d9ac2 that composes to STATUS_OK, a false lifecycle-valid claim for a
switch that never committed.  Fail closed with ``SnapshotError`` instead.
"""

import unittest

from canopy_features.reliability import lock_session_events as lock
from canopy_features.reliability import session_lifecycle_snapshot as snapshot
from canopy_features.reliability import theme_transition_rollback as theme
from canopy_features.windows import focus_intents as focus


class _LedgerWithSnapshot(theme.ThemeTransitionRollback):
    """Bounded hostile source exposing a caller-supplied theme projection."""

    def __init__(self, projected):
        super().__init__()
        self._projected = projected

    def snapshot(self):
        return self._projected


def _compose(state, candidate):
    projected = theme.Snapshot(
        state=state, active="base", candidate=candidate,
        live_resources=frozenset({"r0"}), abandoned_resources=frozenset())
    return snapshot.compose(
        lock.Reconciler(initial_locked=False),
        _LedgerWithSnapshot(projected),
        focus.FocusBroker(lambda *_: True),
    )


class SessionLifecycleThemeStateCandidateTests(unittest.TestCase):
    def test_idle_with_candidate_is_rejected(self):
        with self.assertRaises(snapshot.SnapshotError):
            _compose(theme.IDLE, "candidate")

    def test_prepared_without_candidate_is_rejected(self):
        with self.assertRaises(snapshot.SnapshotError):
            _compose(theme.PREPARED, None)

    def test_idle_without_candidate_stays_ok(self):
        record = _compose(theme.IDLE, None)
        self.assertEqual(record.theme.state, theme.IDLE)
        self.assertEqual(record.status, snapshot.STATUS_OK)

    def test_prepared_with_candidate_blocks(self):
        record = _compose(theme.PREPARED, "candidate")
        self.assertEqual(record.theme.candidate, "candidate")
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)

    def test_hostile_candidate_type_fails_closed(self):
        with self.assertRaises(snapshot.SnapshotError):
            _compose(theme.IDLE, ["candidate"])


if __name__ == "__main__":
    unittest.main()
