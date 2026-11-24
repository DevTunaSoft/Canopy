"""RED/GREEN identity regression: cached SwitcherState.snapshot() with full mutation coverage."""
import unittest

from canopy_features.windows import switcher_state as s


def _state():
    return s.SwitcherState([10, 20, 30], current=10)


class SnapshotCacheTests(unittest.TestCase):
    def test_repeated_reads_return_same_object(self):
        st = _state()
        first = st.snapshot()
        self.assertIsInstance(first, s.SwitchState)
        self.assertIs(first, st.snapshot())

    def test_every_mutator_invalidates(self):
        cases = (
            ("begin", lambda st: st.begin()),
            ("next", lambda st: (st.begin(), st.next())),
            ("previous", lambda st: (st.begin(), st.previous())),
            ("select", lambda st: (st.begin(), st.select(30))),
            ("confirm", lambda st: (st.begin(), st.confirm())),
            ("cancel", lambda st: (st.begin(), st.cancel())),
            ("focus", lambda st: st.focus(20)),
            ("remove", lambda st: st.remove(10)),
        )
        for name, mutate in cases:
            with self.subTest(mutator=name):
                st = _state()
                before = st.snapshot()
                mutate(st)
                after = st.snapshot()
                self.assertIsNot(after, before)
                self.assertEqual(after.active, st.active)
                self.assertEqual(after.current, st.current)
                self.assertEqual(after.selected, st.selected)
                self.assertEqual(after.order, st.order)

    def test_rejected_operations_preserve_identity(self):
        st = _state()
        before = st.snapshot()
        with self.assertRaises(s.SwitcherError):
            st.next()
        with self.assertRaises(s.SwitcherError):
            st.select(999)
        with self.assertRaises(s.SwitcherError):
            st.focus(True)
        self.assertFalse(st.remove(999))
        self.assertIs(st.snapshot(), before)

    def test_snapshot_content_matches_state(self):
        st = _state()
        st.begin()
        st.next()
        snap = st.snapshot()
        self.assertEqual((snap.active, snap.current, snap.selected, snap.order),
                         (True, 10, 20, (10, 20, 30)))

    def test_distinct_instances_do_not_share(self):
        self.assertIsNot(_state().snapshot(), _state().snapshot())


if __name__ == "__main__":
    unittest.main()
