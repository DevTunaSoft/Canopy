"""Wrong-type overflow policy must fail closed at the delivery boundary.

The module documents ``DeliveryError`` for an unsupported overflow policy.
An unhashable caller value (list/dict) reached the frozenset membership test
and leaked ``TypeError`` instead. These tests pin the documented contract and
keep all valid-policy behaviour byte-identical.
"""
import unittest

from canopy_features.reliability.event_delivery_loss import (
    DROPPED_OLDEST, QUEUED, REJECTED, BoundedDeliveryChannel, DeliveryError,
)


class WrongTypePolicyTests(unittest.TestCase):
    def test_unhashable_policies_raise_domain_error(self):
        # list / dict are unhashable; a list that *contains* a valid policy
        # must still be rejected as a wrong type, not matched by equality.
        for policy in ([], ["drop_oldest"], {}, {"policy": "reject_new"}):
            with self.subTest(policy=policy):
                with self.assertRaises(DeliveryError):
                    BoundedDeliveryChannel(policy=policy)

    def test_unhashable_policy_error_message_is_stable(self):
        with self.assertRaises(DeliveryError) as ctx:
            BoundedDeliveryChannel(policy=["drop_oldest"])
        self.assertEqual(str(ctx.exception), "unsupported overflow policy")

    def test_hashable_non_string_policies_unchanged(self):
        # These already failed closed on the base; guard against a fix that
        # accidentally widens the accepted-policy set.
        for policy in (None, 5, 1.5, ("drop_oldest",), b"drop_oldest", True):
            with self.subTest(policy=policy):
                with self.assertRaises(DeliveryError):
                    BoundedDeliveryChannel(policy=policy)

    def test_valid_policies_still_work(self):
        drop = BoundedDeliveryChannel(capacity=1, policy="drop_oldest")
        self.assertTrue(drop.send(1).accepted)
        self.assertEqual(drop.send(2).status, DROPPED_OLDEST)
        reject = BoundedDeliveryChannel(capacity=1, policy="reject_new")
        self.assertTrue(reject.send(1).accepted)
        self.assertEqual(reject.send(2).status, REJECTED)
        self.assertEqual(reject.stats.rejected, 1)

    def test_default_policy_unchanged(self):
        channel = BoundedDeliveryChannel()
        self.assertEqual(channel.send(1).status, QUEUED)
        self.assertEqual(channel.receive().sequence, 1)

    def test_no_state_leak_after_rejected_policy(self):
        with self.assertRaises(DeliveryError):
            BoundedDeliveryChannel(policy=[])
        channel = BoundedDeliveryChannel(capacity=2, policy="reject_new")
        self.assertTrue(channel.send(1).accepted)
        self.assertTrue(channel.send(2).accepted)
        self.assertEqual(channel.pending_count, 2)
        self.assertEqual(channel.stats.sent, 2)


if __name__ == "__main__":
    unittest.main()
