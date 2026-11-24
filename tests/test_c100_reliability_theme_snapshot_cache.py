"""RED/GREEN resource regression: lazy cached theme-ledger snapshot.

Deterministic identity assertions: repeated reads with no state change return
the SAME immutable Snapshot; successful mutations return a fresh one; rejected
operations leave identity untouched.
"""
import unittest

from canopy_features.reliability import theme_transition_rollback as theme


class SnapshotCacheTests(unittest.TestCase):
    def test_repeated_reads_return_same_object(self):
        ledger = theme.ThemeTransitionRollback()
        first = ledger.snapshot()
        self.assertIs(first, ledger.snapshot())
        self.assertIsInstance(first, theme.Snapshot)

    def test_prepare_invalidates(self):
        ledger = theme.ThemeTransitionRollback()
        before = ledger.snapshot()
        self.assertEqual(ledger.prepare("dark", {"r1"}), "PREPARED")
        after = ledger.snapshot()
        self.assertIsNot(after, before)
        self.assertEqual(after.candidate, "dark")

    def test_commit_and_interrupt_invalidate(self):
        ledger = theme.ThemeTransitionRollback()
        ledger.prepare("dark", {"r1"})
        before = ledger.snapshot()
        self.assertEqual(ledger.commit(), "COMMITTED")
        committed = ledger.snapshot()
        self.assertIsNot(committed, before)
        self.assertEqual(committed.state, theme.IDLE)
        ledger.prepare("light", {"r2"})
        before_interrupt = ledger.snapshot()
        self.assertEqual(ledger.interrupt(), "ROLLED_BACK")
        self.assertIsNot(ledger.snapshot(), before_interrupt)

    def test_reclaim_invalidates(self):
        ledger = theme.ThemeTransitionRollback(None, {"r1"})
        ledger.prepare("dark", {"r2"})
        ledger.commit()
        before = ledger.snapshot()
        claimed = ledger.reclaim_abandoned()
        self.assertEqual(claimed, frozenset({"r1"}))
        self.assertIsNot(ledger.snapshot(), before)

    def test_rejected_prepare_preserves_identity(self):
        ledger = theme.ThemeTransitionRollback()
        before = ledger.snapshot()
        self.assertEqual(ledger.prepare(None, None), "INVALID_THEME")
        self.assertIs(ledger.snapshot(), before)
        self.assertEqual(ledger.prepare("dark", 123), "INVALID_RESOURCES")
        self.assertIs(ledger.snapshot(), before)

    def test_content_unchanged(self):
        ledger = theme.ThemeTransitionRollback(None, {"r1"})
        snap = ledger.snapshot()
        self.assertEqual(snap.state, theme.IDLE)
        self.assertEqual(snap.active, None)
        self.assertEqual(snap.live_resources, frozenset({"r1"}))
        self.assertEqual(snap.abandoned_resources, frozenset())
        self.assertTrue(snap.single_owner)


if __name__ == "__main__":
    unittest.main()
