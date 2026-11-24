"""Regression tests for hostile-but-bounded inputs at the app launch preview boundary.

These cover the one audited contract: a hostile but finite wrong-type source
must never produce a false preview-safe (READY) claim or leak a raw built-in
exception. No process launch, shell, filesystem walk or desktop is involved.

Run: python -m unittest tests.test_c100_apps_app_launch_preview_hostile_boundary -v
"""
import unittest
from unittest.mock import patch

from canopy_features.apps import app_launch_preview as preview_mod
from canopy_features.apps.app_launch_preview import (
    REASON_AGREEMENT_MISMATCH,
    REASON_INVALID_INPUT,
    STATUS_DENIED,
    compose_app_launch_preview,
)
from canopy_features.launcher import launcher_intent_summary as intent_mod
from canopy_features.launcher.launcher_intent_summary import (
    STATUS_READY as INTENT_READY,
)

CATALOG = (
    ("org.example.One.desktop", "One"),
    ("org.example.Two.desktop", "Two"),
)
ALLOWED = tuple(app_id for app_id, _ in CATALOG)
ENV_SOURCE = {
    "PATH": "/usr/bin",
    "LANG": "C.UTF-8",
    "SECRET_TOKEN": "do-not-echo-this-value",
}


def compose(query="One", **overrides):
    options = dict(
        allowed_app_ids=ALLOWED,
        env_allow=("PATH", "LANG"),
        env_source=ENV_SOURCE,
    )
    options.update(overrides)
    return compose_app_launch_preview(query, CATALOG, **options)


class HostileAllowlistTests(unittest.TestCase):
    def _terse_denial(self, result):
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertFalse(result.ready)
        self.assertEqual(result.claims, ())
        self.assertEqual(result.match_count, 0)
        self.assertEqual(result.favorite_count, 0)
        self.assertEqual(result.env_count, 0)
        self.assertEqual(result.argv_length, 0)
        payload = repr(result.to_dict())
        self.assertNotIn("do-not-echo-this-value", payload)
        self.assertNotIn("hostile lazy allow source", payload)

    def test_lazy_hostile_allowlist_never_leaks_raw_exception(self):
        # Finite generator: two legal names, then the hostile source raises a
        # plain RuntimeError mid-consumption. The preview boundary must turn
        # that into its own denial, not propagate the built-in to a host.
        def hostile_allow():
            yield "PATH"
            yield "LANG"
            raise RuntimeError("hostile lazy allow source")

        result = compose(env_allow=hostile_allow())
        self.assertEqual(result.reason, REASON_INVALID_INPUT)
        self._terse_denial(result)


class SourceAgreementTests(unittest.TestCase):
    def test_wrong_shaped_intent_argv_is_not_a_safe_preview(self):
        # Same length as a valid GIO argv and every token is a shell-free
        # string, so a length-only agreement check accepts it. The two source
        # decisions actually disagree on argv shape, so READY (and its
        # no_source_disagreement claim) would be a false preview-safe claim.
        hostile = intent_mod.LauncherIntentSummary(
            "One",
            (),
            (),
            "org.example.One.desktop",
            ("a", "b", "c", "org.example.One.desktop"),
            INTENT_READY,
        )
        with patch.object(preview_mod, "summarize_launcher_intent",
                          return_value=hostile):
            result = compose()
        self.assertEqual(result.reason, REASON_AGREEMENT_MISMATCH)
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertFalse(result.ready)
        self.assertEqual(result.claims, ())
        self.assertEqual(result.env_count, 0)
        self.assertEqual(result.argv_length, 0)

    def test_foreign_desktop_id_in_intent_argv_is_not_a_safe_preview(self):
        # A plausible GIO-shaped argv whose app id differs from the selected
        # app id used to build the policy is still a source disagreement.
        hostile = intent_mod.LauncherIntentSummary(
            "One",
            (),
            (),
            "org.example.One.desktop",
            ("gio", "launch", "--", "org.example.Two.desktop"),
            INTENT_READY,
        )
        with patch.object(preview_mod, "summarize_launcher_intent",
                          return_value=hostile):
            result = compose()
        self.assertEqual(result.reason, REASON_AGREEMENT_MISMATCH)
        self.assertFalse(result.ready)
        self.assertEqual(result.claims, ())


if __name__ == "__main__":
    unittest.main()
