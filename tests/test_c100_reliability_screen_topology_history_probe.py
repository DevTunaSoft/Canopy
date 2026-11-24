"""RED/GREEN resource regression for ScreenTopologyModel history storage.

Deterministic structural assertion: history must be a bounded ring buffer
(deque with maxlen) rather than a tuple rebuilt on every apply(). Behaviour
guards pin the public tuple projection, cap, recency and reset semantics.
"""
from collections import deque
import unittest

from canopy_features.reliability import screen_topology_change as topo


def _topology(connector="eDP-1", width=1920, height=1080):
    return topo.Topology([topo.Monitor(connector, width, height, True)])


class HistoryStorageTests(unittest.TestCase):
    def test_history_is_bounded_ring_buffer(self):
        model = topo.ScreenTopologyModel(history_limit=4)
        self.assertIsInstance(model._history, deque)
        self.assertEqual(model._history.maxlen, 4)

    def test_history_public_projection_is_tuple_and_bounded(self):
        model = topo.ScreenTopologyModel(history_limit=3)
        for i in range(10):
            result = model.apply(_topology("eDP-%d" % (i % 2),
                                           1920 + i, 1080))
            self.assertIsInstance(result, topo.RecoveryResult)
        history = model.history
        self.assertIsInstance(history, tuple)
        self.assertEqual(len(history), 3)
        self.assertEqual([r.sequence for r in history], [8, 9, 10])

    def test_reset_clears_history(self):
        model = topo.ScreenTopologyModel(history_limit=3)
        model.apply(_topology())
        model.reset()
        self.assertEqual(model.history, ())
        self.assertIsNone(model.current)
        self.assertEqual(model._sequence, 0)

    def test_invalid_history_limit_fails_closed(self):
        for limit in (0, 65, True, 3.5, None):
            with self.subTest(limit=limit):
                with self.assertRaises(topo.TopologyError):
                    topo.ScreenTopologyModel(history_limit=limit)

    def test_apply_rejects_wrong_type_without_mutation(self):
        model = topo.ScreenTopologyModel(history_limit=3)
        with self.assertRaises(topo.TopologyError):
            model.apply(object())
        self.assertEqual(model.history, ())
        self.assertEqual(model._sequence, 0)


if __name__ == "__main__":
    unittest.main()
