"""RED/GREEN resource regression: DeliveryStats snapshot caching.

Deterministic structural assertion: repeated `stats` reads with no counter
mutation return the SAME immutable object. Behaviour guards pin invalidation
on send/receive, fail-closed no-mutation on rejection, and post-close counts.
"""
import unittest

from canopy_features.reliability import event_delivery_loss as d


class StatsCachingTests(unittest.TestCase):
    def test_stats_is_cached_until_counter_change(self):
        ch = d.BoundedDeliveryChannel(capacity=4, start_sequence=1)
        first = ch.stats
        self.assertIs(first, ch.stats)

    def test_stats_invalidated_after_send(self):
        ch = d.BoundedDeliveryChannel(capacity=4, start_sequence=1)
        before = ch.stats
        ch.send(1, "a")
        after = ch.stats
        self.assertIsNot(after, before)
        self.assertEqual(after.sent, 1)
        self.assertEqual(before.sent, 0)

    def test_stats_invalidated_after_receive(self):
        ch = d.BoundedDeliveryChannel(capacity=4, start_sequence=1)
        ch.send(1, "a")
        before = ch.stats
        delivered = ch.receive()
        after = ch.stats
        self.assertEqual(delivered.status, d.DELIVERED)
        self.assertIsNot(after, before)
        self.assertEqual(after.received, 1)
        self.assertEqual(after.delivered, 1)

    def test_rejected_send_does_not_change_stats(self):
        ch = d.BoundedDeliveryChannel(capacity=4, start_sequence=1)
        before = ch.stats
        with self.assertRaises(d.DeliveryError):
            ch.send(object(), "bad")
        self.assertIs(ch.stats, before)

    def test_close_preserves_counts(self):
        ch = d.BoundedDeliveryChannel(capacity=4, start_sequence=1)
        ch.send(1, "a")
        before = ch.stats
        ch.close()
        self.assertEqual(ch.stats, before)
        with self.assertRaises(d.ChannelClosed):
            ch.send(2, "b")


if __name__ == "__main__":
    unittest.main()
