"""RED/GREEN resource regression: lazy cached focus-decision history tuple."""
import unittest

from canopy_features.windows import focus_intents as f


class HistoryCacheTests(unittest.TestCase):
    def _broker(self):
        return f.FocusBroker(lambda *_: True)

    def test_repeated_reads_return_same_object(self):
        broker = self._broker()
        broker.request_focus(f.FocusIntent("shell", f.WindowRef(1, 1)))
        first = broker.history
        self.assertIsInstance(first, tuple)
        self.assertTrue(first)
        self.assertIs(first, broker.history)

    def test_new_decision_invalidates(self):
        broker = self._broker()
        ref = broker.register_window("files", 1)
        before = broker.history
        decision = broker.request_focus(f.FocusIntent("shell", ref))
        after = broker.history
        self.assertEqual(decision.status, f.GRANTED)
        self.assertIsNot(after, before)
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].status, f.GRANTED)
        self.assertEqual(len(before), 0)

    def test_window_registration_preserves_identity(self):
        broker = self._broker()
        broker.request_focus(f.FocusIntent("shell", f.WindowRef(1, 1)))
        before = broker.history
        ref = broker.register_window("files", 1)
        broker.unregister_window(ref.window_id)
        self.assertIs(broker.history, before)

    def test_rejected_request_preserves_identity(self):
        broker = self._broker()
        broker.request_focus(f.FocusIntent("shell", f.WindowRef(1, 1)))
        before = broker.history
        with self.assertRaises(f.FocusIntentError):
            broker.request_focus(object())
        self.assertIs(broker.history, before)

    def test_history_is_bounded(self):
        broker = self._broker()
        for i in range(100):
            broker.request_focus(f.FocusIntent(
                "shell", f.WindowRef(i + 1, 1)))
        self.assertLessEqual(len(broker.history), f.MAX_HISTORY)
        self.assertIsInstance(broker.history, tuple)


if __name__ == "__main__":
    unittest.main()
