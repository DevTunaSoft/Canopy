"""Offline unit tests for the optional-effects budget policy.

These exercise pure decision logic only. They do not run Qt, a compositor,
a Linux Mint guest or a compiled binary, and grant no release approval.
"""
import inspect
import json
import unittest

import canopy_features.performance.effects_budget as budget_mod
from canopy_features.performance.effects_budget import (
    DEFAULT_PROFILE, EFFECTS, MAX_BUDGET, PROFILES,
    PolicyError, known_effects, resolve,
)


class EffectsBudgetTests(unittest.TestCase):
    def test_defaults_are_hard_low_resource(self):
        plan = resolve()
        self.assertEqual(plan["profile"], DEFAULT_PROFILE)
        self.assertEqual(plan["budget"], 0)
        self.assertTrue(all(value is False for value in plan["decisions"].values()))
        self.assertEqual(plan["enabled"], [])
        self.assertFalse(plan["release_approved"])
        self.assertFalse(plan["desktop_proven"])

    def test_minimal_profile_ignores_requested_budget(self):
        toggles = {name: True for name in known_effects()}
        plan = resolve(toggles, profile="minimal", budget=MAX_BUDGET)
        self.assertEqual(plan["budget"], 0)
        self.assertEqual(plan["enabled"], [])

    def test_infinite_animation_and_perpetual_effects_never_enable(self):
        toggles = {
            "infinite_animation": True,
            "live_wallpaper": True,
            "always_on_blur": True,
        }
        plan = resolve(toggles, profile="high", budget=MAX_BUDGET)
        for name in toggles:
            self.assertFalse(plan["decisions"][name], name)
            self.assertEqual(plan["denied"][name], "perpetual_effect_forbidden")
        self.assertNotIn("infinite_animation", plan["enabled"])
        for rule in ("perpetual_animation_disabled", "always_on_blur_disabled",
                     "live_wallpaper_disabled"):
            self.assertIn(rule, plan["hard_rules"])

    def test_finite_effects_respect_deterministic_budget_ceiling(self):
        toggles = {
            "ui_transitions": True, "dock_hover_scale": True,
            "menu_fade": True, "window_shadow": True, "translucency": True,
        }
        plan = resolve(toggles, profile="high")
        self.assertEqual(plan["budget"], PROFILES["high"])
        self.assertEqual(
            plan["enabled"],
            ["ui_transitions", "dock_hover_scale", "menu_fade", "window_shadow"],
        )
        self.assertEqual(plan["used_budget"], 5)
        self.assertEqual(plan["remaining_budget"], 0)
        self.assertEqual(plan["denied"]["translucency"], "over_budget")
        self.assertLessEqual(plan["used_budget"], plan["budget"])

    def test_lower_budget_override_and_profile_ceiling(self):
        plan = resolve({"translucency": True}, profile="high", budget=1)
        self.assertEqual(plan["budget"], 1)
        self.assertEqual(plan["enabled"], [])
        self.assertEqual(plan["denied"]["translucency"], "over_budget")
        clamped = resolve({}, profile="balanced", budget=MAX_BUDGET)
        self.assertEqual(clamped["budget"], PROFILES["balanced"])

    def test_invalid_effect_toggles_rejected(self):
        too_many = {name: True for name in known_effects()}
        too_many["extra_effect"] = True
        for toggles in (
            [("ui_transitions", True)],
            {"not_an_effect": True},
            {"ui_transitions": 1},
            {"ui_transitions": 0},
            {"ui_transitions": "yes"},
            {"ui_transitions": None},
            {"ui_transitions": 1.0},
            too_many,
        ):
            with self.subTest(toggles=toggles):
                with self.assertRaises(PolicyError):
                    resolve(toggles)

    def test_invalid_profile_and_budget_rejected(self):
        for profile in ("ultra", "", None, 5):
            with self.subTest(profile=profile):
                with self.assertRaises(PolicyError):
                    resolve({}, profile=profile)
        for value in (-1, MAX_BUDGET + 1, True, 1.5, "3"):
            with self.subTest(budget=value):
                with self.assertRaises(PolicyError):
                    resolve({}, profile="high", budget=value)

    def test_plan_is_bounded_json_serialisable_and_pure(self):
        toggles = {name: True for name in known_effects()}
        first = resolve(toggles, profile="high")
        self.assertEqual(first, resolve(toggles, profile="high"))
        self.assertEqual(len(first["decisions"]), len(EFFECTS))
        self.assertTrue(all(type(v) is bool for v in first["decisions"].values()))
        self.assertIsInstance(json.dumps(first, sort_keys=True), str)
        self.assertTrue(toggles["infinite_animation"])

    def test_module_has_no_polling_or_service_primitives(self):
        source = inspect.getsource(budget_mod)
        for token in ("PyQt", "PySide", "QtCore", "subprocess", "threading",
                      "asyncio", "socket", "while True", "time.sleep", "import os"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
