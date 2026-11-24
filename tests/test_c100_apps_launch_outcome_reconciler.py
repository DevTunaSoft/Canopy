"""Tests for pure bounded launch-outcome reconciliation.

Run: python -m unittest tests.test_c100_apps_launch_outcome_reconciler -v
No process launch, I/O, desktop database or Qt runtime is involved.
"""
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.apps import launch_outcome_reconciler as recon_mod
from canopy_features.apps.app_launch_preview import (
    FIXED_CLAIMS as PREVIEW_CLAIMS,
    REASON_OK as PREVIEW_REASON_OK,
    STATUS_READY as PREVIEW_READY,
    AppLaunchPreview,
)
from canopy_features.apps.launch_outcome_reconciler import (
    FIXED_CLAIMS,
    MAX_EVENTS,
    MAX_RETRIES,
    STATUS_GIVE_UP,
    STATUS_IDLE,
    STATUS_RETRY,
    STATUS_SUCCEEDED,
    LaunchExited,
    LaunchFailed,
    LaunchSucceeded,
    OutcomeInputError,
    compose_launch_outcome,
)

APP_ID = "org.example.Example.desktop"
OTHER_ID = "org.example.Other.desktop"


def preview():
    return AppLaunchPreview(PREVIEW_READY, PREVIEW_REASON_OK, 1, 0, 2, 4,
                            PREVIEW_CLAIMS)


def events(*items):
    return compose_launch_outcome(APP_ID, preview(), items)


class ReconciliationTests(unittest.TestCase):
    def test_fixed_negative_claims(self):
        self.assertIsInstance(FIXED_CLAIMS, tuple)
        self.assertTrue(FIXED_CLAIMS)
        for claim in ("no_app_id_echo", "no_reason_text_echo",
                      "no_process_launch", "no_io", "no_geometry_read",
                      "no_visual_change"):
            with self.subTest(claim=claim):
                self.assertIn(claim, FIXED_CLAIMS)

    def test_no_events_is_idle(self):
        result = events()
        self.assertEqual(result.status, STATUS_IDLE)
        self.assertEqual(result.claims, FIXED_CLAIMS)
        self.assertEqual(result.event_count, 0)

    def test_success_event_wins(self):
        result = events(
            LaunchFailed(sequence=1, app_id=APP_ID, reason="spawn-refused"),
            LaunchSucceeded(sequence=2, app_id=APP_ID, pid=4242))
        self.assertEqual(result.status, STATUS_SUCCEEDED)
        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.failure_count, 1)

    def test_clean_exit_is_success(self):
        result = events(LaunchExited(sequence=1, app_id=APP_ID, code=0))
        self.assertEqual(result.status, STATUS_SUCCEEDED)

    def test_one_failure_retries_within_budget(self):
        result = events(
            LaunchFailed(sequence=1, app_id=APP_ID, reason="target-missing"))
        self.assertEqual(result.status, STATUS_RETRY)
        self.assertEqual(result.retry_count, 1)

    def test_retry_budget_exhausted_gives_up(self):
        failures = tuple(LaunchFailed(sequence=i + 1, app_id=APP_ID,
                                      reason="spawn-refused")
                         for i in range(MAX_RETRIES + 1))
        result = events(*failures)
        self.assertEqual(result.status, STATUS_GIVE_UP)
        self.assertEqual(result.retry_count, MAX_RETRIES)
        self.assertEqual(result.failure_count, MAX_RETRIES + 1)

    def test_nonzero_exit_counts_as_failure(self):
        result = events(LaunchExited(sequence=1, app_id=APP_ID, code=1))
        self.assertEqual(result.status, STATUS_RETRY)
        self.assertEqual(result.failure_count, 1)

    def test_other_app_events_are_counted_not_applied(self):
        result = events(
            LaunchFailed(sequence=1, app_id=OTHER_ID, reason="spawn-refused"),
            LaunchSucceeded(sequence=2, app_id=OTHER_ID, pid=1))
        self.assertEqual(result.status, STATUS_IDLE)
        self.assertEqual(result.event_count, 2)
        self.assertEqual(result.relevant_count, 0)

    def test_no_app_id_or_reason_text_is_echoed(self):
        result = events(
            LaunchFailed(sequence=1, app_id=APP_ID, reason="spawn-refused"),
            LaunchSucceeded(sequence=2, app_id=APP_ID, pid=4242))
        payload = repr(result.to_dict())
        for secret in (APP_ID, "spawn-refused", "4242", OTHER_ID):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, payload)

    def test_to_dict_shape(self):
        self.assertEqual(set(events().to_dict()), {
            "status", "reason", "event_count", "relevant_count",
            "success_count", "failure_count", "retry_count", "claims"})

    def test_frozen_record(self):
        with self.assertRaises(FrozenInstanceError):
            events().retry_count = 9

    def test_generator_batch_is_supported(self):
        source = (LaunchFailed(sequence=1, app_id=APP_ID, reason="spawn-refused")
                  for _ in range(1))
        result = compose_launch_outcome(APP_ID, preview(), source)
        self.assertEqual(result.status, STATUS_RETRY)

    def test_module_has_no_io_or_process_api(self):
        with open(recon_mod.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for token in ("subprocess", "Popen", "os.system", "open(", "Path("):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class FailClosedTests(unittest.TestCase):
    def test_invalid_app_id_rejected(self):
        for bad in ("not-an-id", 7, "org.example.X.desktop;rm"):
            with self.subTest(bad=bad):
                with self.assertRaises(OutcomeInputError):
                    compose_launch_outcome(bad, preview(), ())

    def test_non_ready_preview_rejected(self):
        denied = AppLaunchPreview("DENIED", "policy_denied")
        with self.assertRaises(OutcomeInputError):
            compose_launch_outcome(APP_ID, denied, ())

    def test_wrong_event_types_rejected(self):
        for bad in (7, "event", {"sequence": 1}):
            with self.subTest(bad=bad):
                with self.assertRaises(OutcomeInputError):
                    events(bad)

    def test_unknown_failure_reason_rejected(self):
        with self.assertRaises(OutcomeInputError):
            events(LaunchFailed(sequence=1, app_id=APP_ID, reason="unlisted;rm"))

    def test_invalid_sequence_and_pid_rejected(self):
        for bad in (True, -1, "1"):
            with self.subTest(bad=bad):
                with self.assertRaises(OutcomeInputError):
                    events(LaunchSucceeded(sequence=bad, app_id=APP_ID, pid=1))
        with self.assertRaises(OutcomeInputError):
            events(LaunchSucceeded(sequence=1, app_id=APP_ID, pid=True))

    def test_oversized_batch_rejected(self):
        batch = tuple(LaunchFailed(sequence=i + 1, app_id=APP_ID,
                                   reason="spawn-refused")
                      for i in range(MAX_EVENTS + 1))
        with self.assertRaises(OutcomeInputError):
            events(*batch)

    def test_bare_string_batch_rejected(self):
        with self.assertRaises(OutcomeInputError):
            compose_launch_outcome(APP_ID, preview(), "events")


if __name__ == "__main__":
    unittest.main()
