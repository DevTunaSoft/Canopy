"""Offline contract tests for bounded delivery and overflow fallback.

No real Qt, compositor, desktop session or Linux Mint behaviour is claimed.
"""
from pathlib import Path
import unittest

from canopy_core.host_events import HostEvents
from canopy_features.reliability.event_delivery_loss import (
    DROPPED_OLDEST, DUPLICATE, GAP, MAX_CAPACITY, QUEUED, REJECTED, REORDERED,
    DELIVERED, BoundedDeliveryChannel, ChannelClosed, DeliveryError,
)


class BoundedDeliveryChannelTests(unittest.TestCase):
    def test_in_order_delivery_and_bounded_pending(self):
        channel = BoundedDeliveryChannel(capacity=2)
        self.assertTrue(channel.send(1, "a").accepted)
        self.assertEqual(channel.send(2, "b").status, QUEUED)
        self.assertEqual(channel.pending_count, 2)
        first, second = channel.receive(), channel.receive()
        self.assertEqual((first.sequence, first.status, first.payload),
                         (1, DELIVERED, "a"))
        self.assertEqual((second.sequence, second.status, second.payload),
                         (2, DELIVERED, "b"))
        self.assertIsNone(channel.receive())
        self.assertEqual(channel.pending_count, 0)
        self.assertEqual(channel.stats.received, 2)
        self.assertEqual(channel.stats.delivered, 2)

    def test_missed_notifications_are_reported_as_a_bounded_gap(self):
        channel = BoundedDeliveryChannel(capacity=4)
        channel.send(1)
        channel.send(6)
        first, second = channel.receive(), channel.receive()
        self.assertEqual(first.status, DELIVERED)
        self.assertEqual(second.status, GAP)
        self.assertEqual(second.missed_count, 4)
        self.assertEqual(second.missed_sequences, (2, 3, 4, 5))
        self.assertEqual((channel.stats.gaps, channel.stats.missed), (1, 4))

    def test_large_gap_never_materialises_unbounded_sequences(self):
        channel = BoundedDeliveryChannel(capacity=3)
        channel.send(1)
        channel.send(1_000_000)
        first = channel.receive()
        self.assertEqual(first.status, DELIVERED)
        second = channel.receive()
        self.assertEqual(second.status, GAP)
        self.assertEqual(second.missed_count, 999_998)
        self.assertEqual(len(second.missed_sequences), 3)
        self.assertEqual(second.missed_sequences, (2, 3, 4))

    def test_repeated_notification_is_detected_as_duplicate(self):
        channel = BoundedDeliveryChannel(capacity=3)
        channel.send(1)
        channel.send(1)
        first, second = channel.receive(), channel.receive()
        self.assertEqual(first.status, DELIVERED)
        self.assertEqual(second.status, DUPLICATE)
        self.assertEqual(channel.stats.duplicates, 1)
        self.assertEqual(channel.stats.delivered, 1)

    def test_reordered_notification_is_detected(self):
        channel = BoundedDeliveryChannel(capacity=3)
        channel.send(1)
        channel.send(3)
        channel.send(2)
        first, gap, late = channel.receive(), channel.receive(), channel.receive()
        self.assertEqual(first.status, DELIVERED)
        self.assertEqual(gap.status, GAP)
        self.assertEqual(late.sequence, 2)
        self.assertEqual(late.status, REORDERED)
        self.assertEqual(channel.stats.reordered, 1)
        self.assertEqual(channel.stats.gaps, 1)

    def test_drop_oldest_overflow_is_explicit_and_bounded(self):
        channel = BoundedDeliveryChannel(capacity=2, policy="drop_oldest")
        self.assertEqual(channel.send(1).status, QUEUED)
        self.assertEqual(channel.send(2).status, QUEUED)
        overflow = channel.send(3)
        self.assertTrue(overflow.accepted)
        self.assertEqual(overflow.status, DROPPED_OLDEST)
        self.assertEqual(overflow.notice.sequence, 1)
        self.assertEqual(overflow.notice.policy, "drop_oldest")
        self.assertEqual(channel.pending_count, 2)
        first = channel.receive()
        self.assertEqual(first.sequence, 2)
        self.assertEqual(first.status, GAP)
        self.assertEqual(first.missed_count, 1)
        self.assertEqual(first.missed_sequences, (1,))
        self.assertEqual(channel.receive().sequence, 3)
        self.assertEqual(channel.stats.dropped, 1)
        self.assertEqual(len(channel.overflow_notices()), 1)

    def test_reject_new_overflow_is_explicit_and_bounded(self):
        channel = BoundedDeliveryChannel(capacity=1, policy="reject_new")
        self.assertTrue(channel.send(1).accepted)
        refused = channel.send(2)
        self.assertFalse(refused.accepted)
        self.assertEqual(refused.status, REJECTED)
        self.assertEqual(refused.notice.sequence, 2)
        self.assertEqual(channel.pending_count, 1)
        self.assertEqual(channel.receive().sequence, 1)
        self.assertIsNone(channel.receive())
        self.assertEqual(channel.stats.rejected, 1)
        self.assertEqual(channel.stats.dropped, 0)

    def test_notice_history_is_bounded(self):
        channel = BoundedDeliveryChannel(capacity=3, policy="reject_new")
        for sequence in range(1, 40):
            channel.send(sequence)
        self.assertLessEqual(len(channel.overflow_notices()), 3)
        self.assertEqual(channel.stats.rejected, 36)
        self.assertEqual(channel.pending_count, 3)

    def test_close_is_fail_closed_and_releases_state(self):
        channel = BoundedDeliveryChannel(capacity=2)
        channel.send(1)
        channel.send(2)
        channel.send(3)
        channel.close()
        channel.close()
        self.assertTrue(channel.closed)
        self.assertEqual(channel.pending_count, 0)
        self.assertEqual(channel.overflow_notices(), ())
        for action in (lambda: channel.send(4), channel.receive):
            with self.assertRaises(ChannelClosed):
                action()

    def test_validation_rejects_invalid_configuration_and_sequence(self):
        for kwargs in ({"capacity": 0}, {"capacity": MAX_CAPACITY + 1},
                       {"capacity": True}, {"capacity": "2"},
                       {"policy": "drop_all"}, {"policy": None},
                       {"start_sequence": -1}, {"start_sequence": True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(DeliveryError):
                    BoundedDeliveryChannel(**kwargs)
        channel = BoundedDeliveryChannel(start_sequence=1)
        for sequence in (0, -1, True, "1", None, 1.0):
            with self.subTest(sequence=sequence):
                with self.assertRaises(DeliveryError):
                    channel.send(sequence)
        self.assertEqual(channel.stats.sent, 0)

    def test_composes_with_existing_host_event_sequences(self):
        seen = []
        receive = lambda event: seen.append(event.sequence)
        bus = HostEvents({"app.catalog.changed": [receive]})
        bus.subscribe("app.catalog.changed", receive)
        channel = BoundedDeliveryChannel(capacity=2)
        for _ in range(2):
            channel.send(bus.emit("app.catalog.changed", {}).event.sequence)
        bus.close()
        self.assertEqual([channel.receive().sequence for _ in range(2)], [1, 2])
        self.assertEqual(seen, [1, 2])

    def test_no_polling_background_or_os_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/reliability/event_delivery_loss.py").read_text()
        for token in ("QTimer", "time.sleep", "Thread(", "asyncio",
                      "subprocess", "import socket", "importlib"):
            with self.subTest(token=token):
                self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
