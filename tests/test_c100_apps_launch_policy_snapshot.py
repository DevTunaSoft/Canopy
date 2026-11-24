"""Tests for the pure, no-echo launch policy snapshot composer.

Run: python -m unittest tests.test_c100_apps_launch_policy_snapshot -v
No process launch, shell, filesystem mutation or desktop is involved.
"""
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.apps.launch_policy_snapshot import (
    FIXED_CLAIMS,
    REASON_ARGV_REJECTED,
    REASON_ENV_REJECTED,
    REASON_OK,
    REASON_SOURCE_DISAGREEMENT,
    STATUS_APPROVED,
    STATUS_DENIED,
    SnapshotInputError,
    compose_launch_policy_snapshot,
)

APP_ID = "org.example.App.desktop"
ALLOW = ("PATH", "LANG")
SOURCE = {
    "PATH": "/usr/local/bin:/usr/bin",
    "LANG": "C.UTF-8",
    "SECRET_TOKEN": "do-not-echo-this-value",
    "HOME": "/home/someone",
}


class ApprovedTests(unittest.TestCase):
    def test_constants_are_fixed_negative_claims(self):
        self.assertEqual(STATUS_APPROVED, "APPROVED")
        self.assertEqual(STATUS_DENIED, "DENIED")
        self.assertEqual(REASON_OK, "ok")
        self.assertEqual(REASON_ENV_REJECTED, "env_rejected")
        self.assertEqual(REASON_ARGV_REJECTED, "argv_rejected")
        self.assertEqual(REASON_SOURCE_DISAGREEMENT, "source_disagreement")
        self.assertIsInstance(FIXED_CLAIMS, tuple)
        self.assertTrue(FIXED_CLAIMS)
        self.assertTrue(all(type(c) is str for c in FIXED_CLAIMS))
        self.assertIn("no_process_launched", FIXED_CLAIMS)
        self.assertIn("argv_shell_free", FIXED_CLAIMS)
        self.assertIn("env_allowlist_only", FIXED_CLAIMS)

    def test_approved_snapshot_counts_only(self):
        snapshot = compose_launch_policy_snapshot(
            ALLOW, SOURCE, APP_ID, arguments=("--flag",))
        self.assertEqual(snapshot.status, STATUS_APPROVED)
        self.assertEqual(snapshot.reason, REASON_OK)
        self.assertEqual(snapshot.env_count, 2)
        self.assertEqual(snapshot.argv_length, 5)
        self.assertEqual(snapshot.claims, FIXED_CLAIMS)
        self.assertTrue(snapshot.approved)

    def test_no_source_values_or_tokens_are_echoed(self):
        snapshot = compose_launch_policy_snapshot(
            ALLOW, SOURCE, APP_ID, arguments=("--flag",))
        payload = repr(snapshot.to_dict())
        for secret in ("/usr/local/bin:/usr/bin", "C.UTF-8",
                       "do-not-echo-this-value", "/home/someone",
                       "SECRET_TOKEN", APP_ID, "--flag"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, payload)

    def test_empty_source_still_approved(self):
        snapshot = compose_launch_policy_snapshot(ALLOW, {}, APP_ID)
        self.assertEqual(snapshot.env_count, 0)
        self.assertEqual(snapshot.argv_length, 4)
        self.assertEqual(snapshot.claims, FIXED_CLAIMS)

    def test_generator_allowlist_is_supported(self):
        snapshot = compose_launch_policy_snapshot(
            (name for name in ALLOW), SOURCE, APP_ID)
        self.assertEqual(snapshot.env_count, 2)

    def test_to_dict_shape(self):
        snapshot = compose_launch_policy_snapshot(ALLOW, SOURCE, APP_ID)
        self.assertEqual(set(snapshot.to_dict()), {
            "status", "reason", "env_count", "argv_length", "claims"})

    def test_inputs_are_not_mutated(self):
        source = dict(SOURCE)
        args = ["--one", "--two"]
        compose_launch_policy_snapshot(ALLOW, source, APP_ID, arguments=args)
        self.assertEqual(source, SOURCE)
        self.assertEqual(args, ["--one", "--two"])

    def test_record_is_frozen(self):
        snapshot = compose_launch_policy_snapshot(ALLOW, SOURCE, APP_ID)
        with self.assertRaises(FrozenInstanceError):
            snapshot.env_count = 99


class DenialTests(unittest.TestCase):
    def assert_denied(self, snapshot, reason):
        self.assertEqual(snapshot.status, STATUS_DENIED)
        self.assertEqual(snapshot.reason, reason)
        self.assertFalse(snapshot.approved)
        self.assertEqual(snapshot.env_count, 0)
        self.assertEqual(snapshot.argv_length, 0)
        self.assertEqual(snapshot.claims, ())

    def test_credential_shaped_name_denied(self):
        self.assert_denied(
            compose_launch_policy_snapshot(("GITHUB_TOKEN",), SOURCE, APP_ID),
            REASON_ENV_REJECTED)

    def test_credential_handle_name_denied(self):
        self.assert_denied(
            compose_launch_policy_snapshot(("XAUTHORITY",), SOURCE, APP_ID),
            REASON_ENV_REJECTED)

    def test_nul_env_value_denied(self):
        source = {"PATH": "/usr/bin\x00evil"}
        self.assert_denied(
            compose_launch_policy_snapshot(("PATH",), source, APP_ID),
            REASON_ENV_REJECTED)

    def test_oversized_allowlist_denied(self):
        names = tuple("VAR_%02d" % i for i in range(65))
        self.assert_denied(
            compose_launch_policy_snapshot(names, SOURCE, APP_ID),
            REASON_ENV_REJECTED)

    def test_bad_app_id_denied(self):
        self.assert_denied(
            compose_launch_policy_snapshot(ALLOW, SOURCE, "not-a-desktop-id"),
            REASON_ARGV_REJECTED)

    def test_shell_metacharacter_argument_denied(self):
        self.assert_denied(
            compose_launch_policy_snapshot(
                ALLOW, SOURCE, APP_ID, arguments=("app; rm -rf /",)),
            REASON_ARGV_REJECTED)

    def test_unapproved_app_id_denied(self):
        self.assert_denied(
            compose_launch_policy_snapshot(
                ALLOW, SOURCE, APP_ID,
                allowed_app_ids=("org.other.App.desktop",)),
            REASON_ARGV_REJECTED)

    def test_too_many_arguments_denied(self):
        args = tuple("arg%d" % i for i in range(65))
        self.assert_denied(
            compose_launch_policy_snapshot(ALLOW, SOURCE, APP_ID, arguments=args),
            REASON_ARGV_REJECTED)

    def test_denial_payload_has_no_echo(self):
        snapshot = compose_launch_policy_snapshot(("GITHUB_TOKEN",), SOURCE, APP_ID)
        self.assertNotIn("GITHUB_TOKEN", repr(snapshot.to_dict()))
        self.assertNotIn("do-not-echo-this-value", repr(snapshot.to_dict()))


class InputTypeTests(unittest.TestCase):
    def test_wrong_source_type_raises(self):
        with self.assertRaises(SnapshotInputError):
            compose_launch_policy_snapshot(ALLOW, 7, APP_ID)

    def test_wrong_app_id_type_raises(self):
        with self.assertRaises(SnapshotInputError):
            compose_launch_policy_snapshot(ALLOW, SOURCE, 7)


if __name__ == "__main__":
    unittest.main()
