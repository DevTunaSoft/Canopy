"""Hostile-but-bounded preview status label cannot fake launch success.

Run: python -m unittest tests.test_c100_apps_launch_outcome_hostile_status_label -v
No process launch, I/O, desktop database or Qt runtime is involved.
"""
import unittest

from canopy_features.apps.app_launch_preview import (
    FIXED_CLAIMS as PREVIEW_CLAIMS,
    REASON_OK as PREVIEW_REASON_OK,
    STATUS_DENIED,
    STATUS_READY,
    AppLaunchPreview,
)
from canopy_features.apps.launch_outcome_reconciler import (
    STATUS_SUCCEEDED,
    LaunchSucceeded,
    OutcomeInputError,
    compose_launch_outcome,
)

APP_ID = "org.example.Example.desktop"


def ready_preview():
    return AppLaunchPreview(STATUS_READY, PREVIEW_REASON_OK, 1, 0, 0, 4,
                            PREVIEW_CLAIMS)


class HostilePreviewStatusTests(unittest.TestCase):
    def test_lying_status_label_cannot_claim_false_launch_success(self):
        # A hostile str subclass is a bounded wrong-type status label. With an
        # isinstance/!= check it fakes "READY", so a DENIED preview authorises
        # a SUCCEEDED reconciliation: a false launch-success claim.
        class LyingStatus(str):
            def __eq__(self, other):
                return True

            def __ne__(self, other):
                return False

            def __hash__(self):
                return hash(STATUS_READY)

        hostile = AppLaunchPreview(
            LyingStatus(STATUS_DENIED), "policy_denied", 1, 0, 0, 4,
            PREVIEW_CLAIMS)
        with self.assertRaises(OutcomeInputError):
            compose_launch_outcome(
                APP_ID, hostile,
                (LaunchSucceeded(sequence=1, app_id=APP_ID, pid=4242),))

    def test_exploding_status_label_cannot_leak_raw_exception(self):
        # Validation must reject the wrong-type label before comparing it:
        # a hostile __ne__/__hash__ must never escape as a bare RuntimeError.
        class ExplodingStatus(str):
            def __ne__(self, other):
                raise RuntimeError("hostile ne")

            def __hash__(self):
                raise RuntimeError("hostile hash")

        hostile = AppLaunchPreview(ExplodingStatus(STATUS_READY),
                                   PREVIEW_REASON_OK)
        with self.assertRaises(OutcomeInputError):
            compose_launch_outcome(APP_ID, hostile, ())

    def test_normal_ready_preview_still_reconciles(self):
        # Positive control: an exact-str READY preview is unaffected.
        result = compose_launch_outcome(
            APP_ID, ready_preview(),
            (LaunchSucceeded(sequence=1, app_id=APP_ID, pid=4242),))
        self.assertEqual(result.status, STATUS_SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
