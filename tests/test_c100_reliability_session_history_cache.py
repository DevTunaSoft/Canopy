"""RED/GREEN identity regression: cached Reconciler.history tuple."""
import unittest

from canopy_features.reliability import lock_session_events as l


def _event(kind, timestamp, source="unit"):
    return l.SessionEvent(kind, timestamp, source)


class HistoryCacheTests(unittest.TestCase):
    def test_repeated_reads_return_same_object(self):
        rec = l.Reconciler()
        rec.observe(_event(l.SUSPEND, 1))
        first = rec.history
        self.assertIsInstance(first, tuple)
        self.assertTrue(first)
        self.assertIs(first, rec.history)

    def test_rejected_events_preserve_identity(self):
        rec = l.Reconciler()
        rec.observe(_event(l.SUSPEND, 1))
        before = rec.history
        self.assertEqual(rec.observe(_event(l.SUSPEND, 1)).status, l.DUPLICATE)
        self.assertEqual(rec.observe(_event(l.SUSPEND, 0)).status, l.STALE)
        self.assertEqual(rec.observe(_event(l.UNLOCK, 2)).status, l.DEFERRED)
        self.assertEqual(rec.observe(_event(l.LOCK, 2)).status, l.REDUNDANT)
        self.assertIs(rec.history, before)

    def test_transition_invalidates_and_preserves_old_snapshot(self):
        rec = l.Reconciler()
        rec.observe(_event(l.SUSPEND, 1))
        before = rec.history
        outcome = rec.observe(_event(l.RESUME, 2))
        self.assertEqual(outcome.status, l.TRANSITION)
        after = rec.history
        self.assertIsNot(after, before)
        self.assertEqual(len(before), 1)
        self.assertEqual(len(after), 2)
        self.assertIs(after[-1], outcome)
        self.assertIs(after, rec.history)

    def test_bounded_history_limit(self):
        rec = l.Reconciler(history_limit=2)
        for i in range(3):
            rec.observe(_event(l.SUSPEND if i % 2 == 0 else l.RESUME, i))
        self.assertEqual(len(rec.history), 2)
        self.assertEqual([o.event.timestamp for o in rec.history], [1, 2])

    def test_empty_and_distinct_instances(self):
        self.assertEqual(l.Reconciler().history, ())
        first = l.Reconciler()
        second = l.Reconciler()
        first.observe(_event(l.SUSPEND, 1))
        second.observe(_event(l.SUSPEND, 1))
        self.assertIsNot(first.history, second.history)


if __name__ == "__main__":
    unittest.main()
