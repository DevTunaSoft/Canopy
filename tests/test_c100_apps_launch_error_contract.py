"""Offline unit tests for the app launch-error classification contract.

These are pure-Python tests. They do not launch processes, use Qt, GIO, a
window manager or a Linux Mint guest, and make no claim about a working desk.
"""
import unittest
from pathlib import Path

from canopy_features.apps.launch_error_contract import (
    CATEGORIES, ERROR_ACCESS_DENIED, ERROR_NOT_AUTHORIZED, ERROR_NOT_FOUND,
    ERROR_NOT_SUPPORTED, ERROR_PERMISSION_DENIED, ERROR_TIMED_OUT,
    LaunchClassification, LaunchContractError, LaunchOutcome, MAX_TOKEN_BYTES,
    MESSAGE_KEYS, PROTOCOL_VERSION, STATUS_DENIED, STATUS_DISABLED,
    STATUS_FAILED, STATUS_REJECTED, STATUS_REQUESTED, STATUS_TIMED_OUT,
    STATUS_UNAVAILABLE, STATUS_UNKNOWN, classify, status_from_log_marker,
)


class LaunchErrorContractTests(unittest.TestCase):
    def test_confirmed_success_requires_positive_confirmation(self):
        result = classify(LaunchOutcome(STATUS_REQUESTED))
        self.assertEqual(result.category, "success")
        self.assertTrue(result.succeeded)
        self.assertTrue(result.confirmed)
        self.assertFalse(result.actionable)
        self.assertFalse(result.retryable)
        self.assertEqual(result.message_key, "launch.succeeded")
        self.assertEqual(result.version, PROTOCOL_VERSION)

    def test_timeout_is_actionable_and_never_success(self):
        for outcome in (
            LaunchOutcome(STATUS_TIMED_OUT),
            LaunchOutcome(STATUS_FAILED, error_code=ERROR_TIMED_OUT,
                          error_domain="G_IO_ERROR"),
            # A positive-looking status with an expired wait is still a timeout.
            LaunchOutcome(STATUS_REQUESTED, elapsed_ms=5000, timeout_ms=5000),
        ):
            with self.subTest(outcome=outcome):
                result = classify(outcome)
                self.assertEqual(result.category, "timeout")
                self.assertFalse(result.succeeded)
                self.assertTrue(result.confirmed)
                self.assertTrue(result.actionable)
                self.assertTrue(result.retryable)
                self.assertEqual(result.message_key, "launch.timed_out")

    def test_denied_launch_is_actionable_and_not_retryable(self):
        for outcome in (
            LaunchOutcome(STATUS_DENIED),
            LaunchOutcome(STATUS_FAILED, error_code=ERROR_PERMISSION_DENIED,
                          error_domain="G_IO_ERROR"),
            LaunchOutcome(STATUS_FAILED, error_code=ERROR_ACCESS_DENIED),
            LaunchOutcome(STATUS_FAILED, error_code=ERROR_NOT_AUTHORIZED),
        ):
            with self.subTest(outcome=outcome):
                result = classify(outcome)
                self.assertEqual(result.category, "denied")
                self.assertFalse(result.succeeded)
                self.assertTrue(result.confirmed)
                self.assertTrue(result.actionable)
                self.assertFalse(result.retryable)
                self.assertEqual(result.message_key, "launch.permission_denied")

    def test_missing_app_is_actionable(self):
        for outcome in (
            LaunchOutcome(STATUS_UNAVAILABLE),
            LaunchOutcome(STATUS_FAILED, error_code=ERROR_NOT_FOUND,
                          error_domain="G_IO_ERROR"),
        ):
            with self.subTest(outcome=outcome):
                result = classify(outcome)
                self.assertEqual(result.category, "missing_app")
                self.assertFalse(result.succeeded)
                self.assertTrue(result.confirmed)
                self.assertTrue(result.actionable)
                self.assertFalse(result.retryable)
                self.assertEqual(result.message_key, "launch.app_missing")

    def test_disabled_rejected_and_unsupported(self):
        cases = (
            (LaunchOutcome(STATUS_DISABLED), "disabled", "launch.disabled"),
            (LaunchOutcome(STATUS_REJECTED), "invalid_request",
             "launch.invalid_request"),
            (LaunchOutcome(STATUS_FAILED, error_code=ERROR_NOT_SUPPORTED),
             "unsupported", "launch.unsupported"),
        )
        for outcome, category, key in cases:
            with self.subTest(category=category):
                result = classify(outcome)
                self.assertEqual(result.category, category)
                self.assertEqual(result.message_key, key)
                self.assertFalse(result.succeeded)
                self.assertTrue(result.actionable)
                self.assertTrue(result.confirmed)

    def test_absence_of_error_is_not_success(self):
        # Generic failure, unrecognised status and contradictory evidence all
        # fail closed to an unconfirmed UNKNOWN. None may claim success.
        for outcome in (
            LaunchOutcome(STATUS_FAILED),
            LaunchOutcome(STATUS_FAILED, error_code="FAILED"),
            LaunchOutcome("some-unseen-launcher-status"),
            LaunchOutcome(STATUS_REQUESTED, error_code="FAILED"),
            LaunchOutcome(STATUS_REQUESTED, error_domain="G_IO_ERROR"),
        ):
            with self.subTest(outcome=outcome):
                result = classify(outcome)
                self.assertEqual(result.category, "unknown")
                self.assertFalse(result.succeeded)
                self.assertFalse(result.confirmed)
                self.assertFalse(result.actionable)
                self.assertFalse(result.retryable)
                self.assertEqual(result.message_key, "launch.unknown")

    def test_existing_log_markers_map_without_inventing_success(self):
        self.assertEqual(status_from_log_marker("CANOPY_APP_LAUNCH_REQUESTED"),
                         STATUS_REQUESTED)
        self.assertEqual(status_from_log_marker("CANOPY_APP_LAUNCH_FAILED"),
                         STATUS_FAILED)
        self.assertEqual(status_from_log_marker("CANOPY_APP_LAUNCH_UNAVAILABLE"),
                         STATUS_UNAVAILABLE)
        self.assertEqual(status_from_log_marker("CANOPY_APP_LAUNCH_REJECTED"),
                         STATUS_REJECTED)
        unknown_result = classify(
            LaunchOutcome(status_from_log_marker("CANOPY_APP_LAUNCH_OTHER")))
        self.assertEqual(unknown_result.category, "unknown")
        self.assertFalse(unknown_result.succeeded)
        # The genuine REQUESTED marker still requires an error-free outcome.
        self.assertTrue(classify(LaunchOutcome(
            status_from_log_marker("CANOPY_APP_LAUNCH_REQUESTED"))).succeeded)

    def test_input_bounds_and_types(self):
        with self.assertRaises(LaunchContractError):
            LaunchOutcome(None)
        with self.assertRaises(LaunchContractError):
            LaunchOutcome(123)
        with self.assertRaises(LaunchContractError):
            LaunchOutcome(STATUS_REQUESTED, error_code="x" * (MAX_TOKEN_BYTES + 1))
        with self.assertRaises(LaunchContractError):
            LaunchOutcome(STATUS_REQUESTED, elapsed_ms=True)
        with self.assertRaises(LaunchContractError):
            LaunchOutcome(STATUS_REQUESTED, elapsed_ms=-1)
        with self.assertRaises(LaunchContractError):
            LaunchOutcome(STATUS_REQUESTED, timeout_ms=86_400_001)
        with self.assertRaises(LaunchContractError):
            classify({"status": STATUS_REQUESTED})

    def test_results_are_immutable_and_message_keys_complete(self):
        outcome = LaunchOutcome(STATUS_TIMED_OUT)
        result = classify(outcome)
        self.assertIsInstance(result, LaunchClassification)
        with self.assertRaises(Exception):
            result.category = "success"
        with self.assertRaises(Exception):
            outcome.status = STATUS_UNKNOWN
        self.assertEqual(set(MESSAGE_KEYS), set(CATEGORIES))
        for category in CATEGORIES:
            self.assertTrue(MESSAGE_KEYS[category].startswith("launch."))

    def test_no_polling_services_or_privileged_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/apps/launch_error_contract.py").read_text()
        for forbidden in ("subprocess", "import socket", "QTimer", "time.sleep",
                          "Thread(", "asyncio", "importlib", "os.system",
                          "import glib", "import gi"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
