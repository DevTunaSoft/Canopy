"""Offline unit tests for resource-profile feature-override precedence.

No real Linux Mint, Qt, compositor or desktop session is exercised here.
"""
from pathlib import Path
import unittest

from canopy_features.performance.feature_overrides import (
    FEATURES, PROFILES, SCOPES, FeatureOverride, OverrideError,
    ProfileFeatureResolver,
)


def overrides(*entries):
    return [FeatureOverride(*entry) for entry in entries]


class FeatureOverrideTests(unittest.TestCase):
    def test_profiles_and_features_are_bounded(self):
        self.assertEqual(len(PROFILES), 6)
        self.assertEqual(PROFILES[-1], "auto")
        self.assertEqual(SCOPES, ("baseline", "profile", "user"))
        self.assertEqual(len(FEATURES), len(set(FEATURES)))

    def test_defaults_all_features_off(self):
        resolver = ProfileFeatureResolver()
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.assertEqual(resolver.effective(profile),
                                 {feature: False for feature in FEATURES})

    def test_precedence_baseline_then_profile_then_user(self):
        resolver = ProfileFeatureResolver(overrides(
            ("baseline", "blur_effects", False),
            ("profile", "blur_effects", False, "balanced"),
            ("user", "blur_effects", True),
        ))
        self.assertTrue(resolver.resolve("balanced", "blur_effects"))
        self.assertTrue(resolver.resolve("powersaver", "blur_effects"))
        resolver_no_user = ProfileFeatureResolver(overrides(
            ("baseline", "blur_effects", True),
            ("profile", "blur_effects", False, "balanced"),
        ))
        self.assertFalse(resolver_no_user.resolve("balanced", "blur_effects"))
        self.assertTrue(resolver_no_user.resolve("powersaver", "blur_effects"))

    def test_profile_override_applies_only_to_named_profile(self):
        resolver = ProfileFeatureResolver(overrides(
            ("profile", "wallpaper_animation", True, "performance"),
        ))
        self.assertTrue(resolver.resolve("performance", "wallpaper_animation"))
        self.assertFalse(resolver.resolve("balanced", "wallpaper_animation"))
        self.assertFalse(resolver.resolve("auto", "wallpaper_animation"))

    def test_auto_profile_is_valid_and_accepts_its_own_layer(self):
        resolver = ProfileFeatureResolver(overrides(
            ("baseline", "search_indexing", True),
            ("profile", "search_indexing", False, "auto"),
            ("user", "live_wallpaper", True),
        ))
        self.assertFalse(resolver.resolve("auto", "search_indexing"))
        self.assertTrue(resolver.resolve("balanced", "search_indexing"))
        self.assertTrue(resolver.resolve("auto", "live_wallpaper"))

    def test_conflicting_same_scope_profile_feature_raises(self):
        with self.assertRaisesRegex(OverrideError, "conflict"):
            ProfileFeatureResolver(overrides(
                ("profile", "dock_animation", True, "balanced"),
                ("profile", "dock_animation", False, "balanced"),
            ))

    def test_identical_duplicate_override_is_idempotent(self):
        resolver = ProfileFeatureResolver(overrides(
            ("user", "blur_effects", True),
            ("user", "blur_effects", True),
        ))
        self.assertTrue(resolver.resolve("maximum", "blur_effects"))

    def test_baseline_and_user_are_distinct_scopes_not_a_conflict(self):
        resolver = ProfileFeatureResolver(overrides(
            ("baseline", "blur_effects", False),
            ("user", "blur_effects", True),
        ))
        self.assertTrue(resolver.resolve("balanced", "blur_effects"))

    def test_same_feature_different_profiles_is_not_a_conflict(self):
        resolver = ProfileFeatureResolver(overrides(
            ("profile", "blur_effects", True, "powersaver"),
            ("profile", "blur_effects", False, "performance"),
        ))
        self.assertTrue(resolver.resolve("powersaver", "blur_effects"))
        self.assertFalse(resolver.resolve("performance", "blur_effects"))

    def test_invalid_profile_values_rejected(self):
        resolver = ProfileFeatureResolver()
        for profile in ("ultra", "", "Balanced", True, None, 1, [], {}):
            with self.subTest(profile=repr(profile)):
                with self.assertRaises(OverrideError):
                    resolver.resolve(profile, "blur_effects")
                with self.assertRaises(OverrideError):
                    resolver.effective(profile)
                with self.assertRaises(OverrideError):
                    ProfileFeatureResolver(overrides(
                        ("profile", "blur_effects", True, profile),
                    ))

    def test_invalid_feature_scope_value_and_entry_rejected(self):
        resolver = ProfileFeatureResolver()
        for feature in ("gravity", "", True, None, 5):
            with self.subTest(feature=repr(feature)):
                with self.assertRaises(OverrideError):
                    resolver.resolve("balanced", feature)
        bad_inputs = [
            overrides(("profile", "gravity", True, "balanced")),
            overrides(("turbo", "blur_effects", True, "balanced")),
            overrides(("baseline", "blur_effects", 1)),
            overrides(("baseline", "blur_effects", 0)),
            overrides(("baseline", "blur_effects", "yes")),
            overrides(("baseline", "blur_effects", None)),
            overrides(("baseline", "blur_effects", True, "balanced")),
            [("baseline", "blur_effects", True)],
            {"scope": "baseline"},
        ]
        for entries in bad_inputs:
            with self.subTest(entries=repr(entries)):
                with self.assertRaises(OverrideError):
                    ProfileFeatureResolver(entries)

    def test_resolution_independent_of_override_order(self):
        entries = overrides(
            ("baseline", "blur_effects", False),
            ("profile", "blur_effects", True, "performance"),
            ("user", "dock_animation", True),
        )
        a = ProfileFeatureResolver(entries)
        b = ProfileFeatureResolver(list(reversed(entries)))
        self.assertEqual(a.effective("performance"), b.effective("performance"))
        self.assertEqual(a.effective("auto"), b.effective("auto"))

    def test_effective_returns_independent_snapshot(self):
        resolver = ProfileFeatureResolver(overrides(
            ("user", "blur_effects", True),
        ))
        snapshot = resolver.effective("balanced")
        snapshot["blur_effects"] = False
        self.assertTrue(resolver.resolve("balanced", "blur_effects"))

    def test_no_polling_threads_or_service_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/performance/feature_overrides.py").read_text()
        for token in ("import socket", "subprocess", "QTimer", "time.sleep",
                      "Thread(", "asyncio", "requests", "open("):
            with self.subTest(token=token):
                self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
