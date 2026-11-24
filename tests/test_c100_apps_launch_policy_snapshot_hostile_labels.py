"""Fail-closed contract for hostile-but-bounded wrong-type labels.

The compose layer is a launch-policy trust boundary: a caller-supplied allowlist
or token iterable may contain a wrong-type label and then fail while being read.
Such input is finite and offline, but if the underlying failure escapes as a raw
built-in exception a host bridge can mistake it for an internal crash -- or a
caller can use the exception to bypass the bounded DENIED decision record.

Every input here is synthetic; no process, shell, socket, file or desktop is
touched. No real credential or real desktop id is used.
"""
import unittest

from canopy_features.apps.launch_policy_snapshot import (
    FIXED_CLAIMS,
    REASON_ARGV_REJECTED,
    REASON_ENV_REJECTED,
    REASON_OK,
    STATUS_APPROVED,
    STATUS_DENIED,
    compose_launch_policy_snapshot,
)

APP_ID = "org.example.App.desktop"
ALLOW = ("PATH", "LANG")
SOURCE = {"PATH": "/usr/bin", "LANG": "C.UTF-8"}


class HostileLabelIterable:
    """Bounded: one valid label, one wrong-type label, then a hard failure."""

    def __init__(self, good, exc=None):
        self.good = good
        self.exc = exc if exc is not None else RuntimeError("hostile label source")
        self.read = 0

    def __iter__(self):
        yield self.good
        self.read += 1
        yield 42  # wrong-type label: an int where a str is required
        self.read += 1
        raise self.exc


class HostileLabelTests(unittest.TestCase):
    def assert_bounded_denial(self, snapshot, reason):
        self.assertEqual(snapshot.status, STATUS_DENIED)
        self.assertEqual(snapshot.reason, reason)
        self.assertFalse(snapshot.approved)
        self.assertEqual(snapshot.env_count, 0)
        self.assertEqual(snapshot.argv_length, 0)
        self.assertEqual(snapshot.claims, ())
        payload = repr(snapshot.to_dict())
        for marker in ("/usr/bin", "C.UTF-8", "42", "hostile label source"):
            self.assertNotIn(marker, payload)

    def test_env_allow_hostile_wrong_type_label_fails_closed(self):
        allow = HostileLabelIterable("PATH")
        snapshot = compose_launch_policy_snapshot(allow, SOURCE, APP_ID)
        self.assertGreaterEqual(allow.read, 1)
        self.assert_bounded_denial(snapshot, REASON_ENV_REJECTED)

    def test_env_allow_hostile_oserror_fails_closed(self):
        allow = HostileLabelIterable("PATH", OSError("allowlist unavailable"))
        snapshot = compose_launch_policy_snapshot(allow, SOURCE, APP_ID)
        self.assert_bounded_denial(snapshot, REASON_ENV_REJECTED)

    def test_app_allowlist_hostile_wrong_type_label_fails_closed(self):
        allowed = HostileLabelIterable(APP_ID)
        snapshot = compose_launch_policy_snapshot(
            ALLOW, SOURCE, APP_ID, allowed_app_ids=allowed)
        self.assertGreaterEqual(allowed.read, 1)
        self.assert_bounded_denial(snapshot, REASON_ARGV_REJECTED)

    def test_app_allowlist_hostile_runtime_error_fails_closed(self):
        allowed = HostileLabelIterable(APP_ID, RuntimeError("boom"))
        snapshot = compose_launch_policy_snapshot(
            ALLOW, SOURCE, APP_ID, allowed_app_ids=allowed)
        self.assert_bounded_denial(snapshot, REASON_ARGV_REJECTED)

    def test_arguments_hostile_wrong_type_label_fails_closed(self):
        args = HostileLabelIterable("--flag")
        snapshot = compose_launch_policy_snapshot(
            ALLOW, SOURCE, APP_ID, arguments=args)
        self.assertGreaterEqual(args.read, 1)
        self.assert_bounded_denial(snapshot, REASON_ARGV_REJECTED)

    def test_arguments_hostile_value_error_fails_closed(self):
        args = HostileLabelIterable("--flag", ValueError("boom"))
        snapshot = compose_launch_policy_snapshot(
            ALLOW, SOURCE, APP_ID, arguments=args)
        self.assert_bounded_denial(snapshot, REASON_ARGV_REJECTED)

    def test_plain_wrong_type_labels_still_fail_closed(self):
        self.assert_bounded_denial(
            compose_launch_policy_snapshot(("PATH", 42), SOURCE, APP_ID),
            REASON_ENV_REJECTED)
        self.assert_bounded_denial(
            compose_launch_policy_snapshot(
                ALLOW, SOURCE, APP_ID, allowed_app_ids=(APP_ID, 42)),
            REASON_ARGV_REJECTED)
        self.assert_bounded_denial(
            compose_launch_policy_snapshot(
                ALLOW, SOURCE, APP_ID, arguments=("--flag", 42)),
            REASON_ARGV_REJECTED)

    def test_valid_labels_still_approved(self):
        snapshot = compose_launch_policy_snapshot(
            ALLOW, SOURCE, APP_ID,
            arguments=("--flag",),
            allowed_app_ids=(APP_ID,))
        self.assertEqual(snapshot.status, STATUS_APPROVED)
        self.assertEqual(snapshot.reason, REASON_OK)
        self.assertEqual(snapshot.env_count, 2)
        self.assertEqual(snapshot.argv_length, 5)
        self.assertEqual(snapshot.claims, FIXED_CLAIMS)


if __name__ == "__main__":
    unittest.main()
