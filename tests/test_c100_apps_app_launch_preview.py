"""Tests for the pure, no-echo application launch preview composer.

Run: python -m unittest tests.test_c100_apps_app_launch_preview -v
No process launch, shell, filesystem walk or desktop is involved.
"""
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from canopy_features.apps import app_launch_preview as preview_mod
from canopy_features.apps.app_launch_preview import (
    FIXED_CLAIMS,
    REASON_AGREEMENT_MISMATCH,
    REASON_INVALID_INPUT,
    REASON_NOT_APPROVED,
    REASON_NO_MATCH,
    REASON_OK,
    REASON_POLICY_DENIED,
    STATUS_DENIED,
    STATUS_NOT_APPROVED,
    STATUS_NO_MATCH,
    STATUS_READY,
    AppLaunchPreview,
    compose_app_launch_preview,
)
from canopy_features.apps.launch_policy_snapshot import (
    REASON_OK as SNAPSHOT_REASON_OK,
    STATUS_APPROVED as SNAPSHOT_APPROVED,
    FIXED_CLAIMS as SNAPSHOT_CLAIMS,
    LaunchPolicySnapshot,
)
from canopy_features.launcher.launcher_intent_summary import (
    STATUS_NOT_APPROVED as INTENT_NOT_APPROVED,
    STATUS_NO_MATCH as INTENT_NO_MATCH,
    STATUS_READY as INTENT_READY,
)

CATALOG = (
    ("org.example.One.desktop", "One"),
    ("org.example.Two.desktop", "Two"),
)
ALLOWED = tuple(app_id for app_id, _ in CATALOG)
ENV_ALLOW = ("PATH", "LANG")
ENV_SOURCE = {
    "PATH": "/usr/local/bin:/usr/bin",
    "LANG": "C.UTF-8",
    "SECRET_TOKEN": "do-not-echo-this-value",
}


def compose(query="One", **overrides):
    options = dict(
        allowed_app_ids=ALLOWED,
        env_allow=ENV_ALLOW,
        env_source=ENV_SOURCE,
    )
    options.update(overrides)
    return compose_app_launch_preview(query, CATALOG, **options)


class ApprovedTests(unittest.TestCase):
    def test_constants_are_fixed_negative_claims(self):
        self.assertEqual(STATUS_READY, "READY")
        self.assertEqual(STATUS_DENIED, "DENIED")
        self.assertEqual(STATUS_NO_MATCH, "NO_MATCH")
        self.assertEqual(STATUS_NOT_APPROVED, "NOT_APPROVED")
        self.assertEqual(REASON_OK, "ok")
        self.assertIsInstance(FIXED_CLAIMS, tuple)
        self.assertTrue(FIXED_CLAIMS)
        self.assertTrue(all(type(c) is str for c in FIXED_CLAIMS))
        for claim in ("no_process_launched", "no_value_echo",
                      "no_shell_metacharacters", "no_source_disagreement"):
            with self.subTest(claim=claim):
                self.assertIn(claim, FIXED_CLAIMS)

    def test_approved_preview_counts_only(self):
        result = compose()
        self.assertEqual(result, AppLaunchPreview(
            STATUS_READY, REASON_OK, match_count=1, favorite_count=0,
            env_count=2, argv_length=4, claims=FIXED_CLAIMS))
        self.assertTrue(result.ready)

    def test_favorites_are_counted_not_echoed(self):
        result = compose(favorites=("org.example.Two.desktop",))
        self.assertEqual(result.favorite_count, 1)
        self.assertNotIn("org.example.Two.desktop", repr(result.to_dict()))

    def test_no_source_values_or_tokens_are_echoed(self):
        payload = repr(compose().to_dict())
        for secret in ("/usr/local/bin:/usr/bin", "C.UTF-8",
                       "do-not-echo-this-value", "SECRET_TOKEN",
                       "org.example.One.desktop", "One"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, payload)

    def test_to_dict_shape(self):
        self.assertEqual(set(compose().to_dict()), {
            "status", "reason", "match_count", "favorite_count",
            "env_count", "argv_length", "claims"})

    def test_record_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            compose().env_count = 99

    def test_inputs_are_not_mutated(self):
        source = dict(ENV_SOURCE)
        compose(env_source=source)
        self.assertEqual(source, ENV_SOURCE)

    def test_module_never_imports_a_process_spawner(self):
        with open(preview_mod.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("Popen", source)
        self.assertNotIn("os.system", source)


class DenialTests(unittest.TestCase):
    def assert_terse_denial(self, result, status, reason):
        self.assertEqual(result.status, status)
        self.assertEqual(result.reason, reason)
        self.assertFalse(result.ready)
        self.assertEqual(result.match_count, 0)
        self.assertEqual(result.favorite_count, 0)
        self.assertEqual(result.env_count, 0)
        self.assertEqual(result.argv_length, 0)
        self.assertEqual(result.claims, ())

    def test_no_match(self):
        self.assert_terse_denial(compose("zzz"), STATUS_NO_MATCH, REASON_NO_MATCH)
        self.assertEqual(compose("zzz").status, INTENT_NO_MATCH)

    def test_not_approved_by_host(self):
        result = compose(allowed_app_ids=("org.other.App.desktop",))
        self.assert_terse_denial(result, STATUS_NOT_APPROVED, REASON_NOT_APPROVED)
        self.assertEqual(result.status, INTENT_NOT_APPROVED)

    def test_policy_denied(self):
        self.assert_terse_denial(
            compose(env_allow=("GITHUB_TOKEN",)),
            STATUS_DENIED, REASON_POLICY_DENIED)

    def test_invalid_query_is_denied_without_echo(self):
        result = compose(7)
        self.assert_terse_denial(result, STATUS_DENIED, REASON_INVALID_INPUT)
        self.assertNotIn("7", repr(result.to_dict()))

    def test_agreement_mismatch_is_fault_injected(self):
        wrong = LaunchPolicySnapshot(
            SNAPSHOT_APPROVED, SNAPSHOT_REASON_OK,
            env_count=2, argv_length=99, claims=SNAPSHOT_CLAIMS)
        with patch.object(preview_mod, "compose_launch_policy_snapshot",
                          return_value=wrong):
            result = compose()
        self.assert_terse_denial(
            result, STATUS_DENIED, REASON_AGREEMENT_MISMATCH)

    def test_denial_has_no_echo(self):
        payload = repr(compose(env_allow=("GITHUB_TOKEN",)).to_dict())
        self.assertNotIn("GITHUB_TOKEN", payload)
        self.assertNotIn("do-not-echo-this-value", payload)


if __name__ == "__main__":
    unittest.main()
