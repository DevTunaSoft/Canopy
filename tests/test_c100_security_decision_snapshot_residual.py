"""Residual cross-field contract tests for the security decision snapshot.

The metadata status label and its capability count are two views of the same
validate-only boundary decision. ``to_safe_metadata`` emits ``SAFE`` only with
a non-empty capability set and emits a rejection with a zero count. A forged
record that pairs independently-valid tokens across those two fields would
therefore report a decision the real boundary can never make. These tests pin
that cross-field invariant at the public serialization boundary.

Run: python -m unittest tests.test_c100_security_decision_snapshot_residual -v
"""
import unittest

from canopy_features.security import privilege_boundary as priv
from canopy_features.security.security_decision_snapshot import (
    SCHEMA,
    SecurityDecisionSnapshot,
    SnapshotError,
)


def forge(**overrides):
    values: dict = dict(
        schema=SCHEMA,
        uri_status="PERMITTED",
        privilege_status="ALLOWED",
        privilege_reason=priv.ALLOWED,
        metadata_status="SAFE",
        metadata_capability_count=2,
    )
    values.update(overrides)
    return SecurityDecisionSnapshot(**values)


class MetadataCrossFieldTests(unittest.TestCase):
    def test_safe_label_with_zero_capabilities_fails_closed(self):
        # SAFE with a zero count is a false decision-safe claim: the real
        # boundary never reports SAFE without at least one valid capability.
        with self.assertRaises(SnapshotError):
            forge(metadata_status="SAFE", metadata_capability_count=0).as_dict()

    def test_rejected_label_with_capabilities_fails_closed(self):
        # REJECTED always yields a zero count; a nonzero count beside REJECTED
        # is a contradictory claim about the metadata boundary's decision.
        with self.assertRaises(SnapshotError):
            forge(metadata_status="REJECTED",
                  metadata_capability_count=1).as_dict()

    def test_consistent_metadata_pairs_still_serialize(self):
        # Guard against over-rejection: the two real, self-consistent pairs
        # must remain serializable.
        safe = forge(metadata_status="SAFE",
                     metadata_capability_count=2).as_dict()
        self.assertEqual(safe["metadata_status"], "SAFE")
        self.assertEqual(safe["metadata_capability_count"], 2)
        rejected = forge(metadata_status="REJECTED",
                         metadata_capability_count=0).as_dict()
        self.assertEqual(rejected["metadata_status"], "REJECTED")
        self.assertEqual(rejected["metadata_capability_count"], 0)

    def test_each_safe_count_is_consistent(self):
        # Every positive, in-bound count is a legitimate SAFE projection.
        for count in range(1, 8):
            with self.subTest(count=count):
                out = forge(metadata_status="SAFE",
                            metadata_capability_count=count).as_dict()
                self.assertEqual(out["metadata_capability_count"], count)

    def test_privilege_contradiction_remains_covered(self):
        # Neighbouring cross-field guard must stay intact.
        with self.assertRaises(SnapshotError):
            forge(privilege_status="ALLOWED",
                  privilege_reason=priv.DENIED_ELEVATION).as_dict()


if __name__ == "__main__":
    unittest.main()
