"""Regression: a wrong-type privilege label must never fail open.

``evaluate``/``authorize`` take an ``euid`` privilege label that callers may
read from configuration or an injected host probe.  The old code compared it
directly with ``euid == 0``.  A bounded hostile-but-wrong-type label therefore
either compared unequal to 0 and produced ALLOWED (a false privilege-safe
claim) or raised a raw exception from a custom ``__eq__``.  Both are denied
fail-closed at the boundary now.

Pure Python, host portable; no process is spawned and no credential changes.
"""

import unittest
from unittest.mock import patch

from canopy_features.security import privilege_boundary as pb


EUID = 1000

# Every one of these currently compares unequal to 0, so the old boundary
# returns ALLOWED for a harmless action even though the caller supplied a
# privilege label that is not a valid euid at all.
FAIL_OPEN_LABELS = (
    "0", "root", "elevated", "restricted", "000", "1000",
    True, 1.0,
    [], (), {}, {0: 1}, frozenset(),
)


class _ExplodingLabel:
    """Bounded hostile privilege label: any equality probe raises."""

    def __eq__(self, other):
        raise RuntimeError("hostile privilege label comparison")


class WrongTypePrivilegeLabelTests(unittest.TestCase):
    def test_string_bool_and_container_labels_fail_closed(self):
        for label in FAIL_OPEN_LABELS:
            with self.subTest(label=label):
                decision = pb.evaluate(["nemo", "--new-window"], euid=label)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, pb.DENIED_INVALID_EUID)

    def test_authorize_denies_wrong_type_label_with_stable_reason(self):
        for label in ("elevated", True, []):
            with self.subTest(label=label):
                with self.assertRaises(pb.PrivilegeDenied) as context:
                    pb.authorize(["nemo"], euid=label)
                self.assertEqual(context.exception.reason, pb.DENIED_INVALID_EUID)
                self.assertEqual(str(context.exception), context.exception.reason)
                self.assertNotIn("nemo", str(context.exception))

    def test_exploding_label_does_not_leak_raw_exception(self):
        # The old `euid == 0` probe invoked the hostile __eq__ and raised
        # RuntimeError out of both public entry points.
        decision = pb.evaluate(["nemo"], euid=_ExplodingLabel())
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, pb.DENIED_INVALID_EUID)
        with self.assertRaises(pb.PrivilegeDenied) as context:
            pb.authorize(["nemo"], euid=_ExplodingLabel())
        self.assertEqual(context.exception.reason, pb.DENIED_INVALID_EUID)

    def test_exploding_label_from_injected_host_probe_is_contained(self):
        with patch.object(pb, "current_euid", return_value=_ExplodingLabel()):
            decision = pb.evaluate(["nemo"])
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason, pb.DENIED_INVALID_EUID)

    def test_valid_labels_still_have_their_original_decision(self):
        self.assertTrue(pb.evaluate(["nemo"], euid=1000).allowed)
        self.assertEqual(
            pb.evaluate(["nemo"], euid=0).reason, pb.DENIED_INHERITED_ROOT
        )
        # None means "elevation detection unavailable"; argument denial still
        # applies, matching the documented Windows contract.
        self.assertTrue(pb.evaluate(["nemo"], euid=None).allowed)
        with patch.object(pb, "current_euid", return_value=None):
            self.assertTrue(pb.evaluate(["nemo"]).allowed)
            self.assertEqual(
                pb.evaluate(["sudo", "nemo"]).reason, pb.DENIED_ELEVATION
            )


if __name__ == "__main__":
    unittest.main()
