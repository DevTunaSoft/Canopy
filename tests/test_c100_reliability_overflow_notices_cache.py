"""RED/GREEN resource regression: lazy cached overflow-notice tuple."""
import unittest

from canopy_features.reliability import event_delivery_loss as d


class NoticeCacheTests(unittest.TestCase):
    def _channel(self):
        ch = d.BoundedDeliveryChannel(capacity=1, policy="drop_oldest",
                                      start_sequence=1)
        ch.send(1, "a")
        ch.send(2, "b")  # overflow: one notice for dropped seq 1
        return ch

    def test_repeated_reads_return_same_object(self):
        ch = self._channel()
        first = ch.overflow_notices()
        self.assertIsInstance(first, tuple)
        self.assertTrue(first)
        self.assertIs(first, ch.overflow_notices())

    def test_new_overflow_invalidates(self):
        ch = self._channel()
        before = ch.overflow_notices()
        ch.send(3, "c")
        after = ch.overflow_notices()
        self.assertIsNot(after, before)
        self.assertEqual(after[-1].sequence, 2)
        self.assertEqual(before[-1].sequence, 1)
        self.assertEqual(len(after), 1)

    def test_receive_preserves_identity(self):
        ch = self._channel()
        before = ch.overflow_notices()
        ch.receive()
        self.assertIs(ch.overflow_notices(), before)

    def test_close_clears_notices(self):
        ch = self._channel()
        ch.close()
        self.assertEqual(ch.overflow_notices(), ())
        with self.assertRaises(d.ChannelClosed):
            ch.send(9, "z")

    def test_notice_content_unchanged(self):
        ch = self._channel()
        notice = ch.overflow_notices()[0]
        self.assertEqual(notice.sequence, 1)
        self.assertEqual(notice.policy, "drop_oldest")
        self.assertEqual(notice.pending_count, 0)
        self.assertEqual(ch.pending_count, 1)


if __name__ == "__main__":
    unittest.main()
