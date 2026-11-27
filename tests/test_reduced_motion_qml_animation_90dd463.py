"""Focused offline contract for reduced-motion policy exposed to Classic QML.

This is a source-level gate only: it never compiles Qt, launches a window,
starts a screen reader or claims Mint/visual acceptance. It proves that the
native accessibility hint is mapped into the documented preference domain,
that a reduction can never be overridden, and that QML animation durations
have a single policy entry point which collapses to zero when reduced.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
MAIN_CPP = CLASSIC / "main.cpp"
POLICY_H = CLASSIC / "ReducedMotionPolicy.h"

# No presentation file is edited by this change: the frozen Classic visual
# inputs must stay byte-identical and no new animation machinery is introduced.
FORBIDDEN_ANIMATIONS = (
    "NumberAnimation", "PropertyAnimation", "SequentialAnimation",
    "ParallelAnimation", "PauseAnimation", "SmoothedAnimation",
    "SpringAnimation", "AnchorAnimation", "Behavior on", "ShaderEffect",
)


def source(path: Path) -> str:
    """Return normalized text; an absent file fails the contract, not setUp."""
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


class ReducedMotionQmlBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = source(POLICY_H)
        self.main = source(MAIN_CPP)

    def test_native_hint_is_mapped_into_the_documented_domain(self):
        for marker in (
            "QGuiApplication", "QStyleHints", "QAccessibilityHints",
            "QT_VERSION_CHECK(6, 12, 0)", "motionPreference()",
            "Qt::MotionPreference::ReducedMotion",
            'QStringLiteral("reduce")', 'QStringLiteral("unset")',
        ):
            with self.subTest(marker=marker):
                self.assertTrue(marker in self.policy, "policy marker missing: " + marker)

    def test_no_preference_fails_safe_and_reduce_cannot_be_overridden(self):
        self.assertTrue(self.policy, "ReducedMotionPolicy.h is missing")
        body = re.search(r"inline bool reduced\([^)]*\) \{(.*?)\n\}",
                         self.policy, re.DOTALL)
        self.assertIsNotNone(body, "pure reduced() resolver is missing")
        text = body.group(1)
        self.assertIn("normalize(native)", text)
        self.assertIn("normalize(user)", text)
        # A REDUCE from any source is authoritative; FULL never re-enables it.
        self.assertRegex(text, r'n\s*==\s*QLatin1String\(REDUCE\)')
        self.assertRegex(text, r'u\s*==\s*QLatin1String\(REDUCE\)')
        self.assertIn("return true", text)
        # No explicit source at all must fail safe to reduce, never to motion.
        self.assertTrue(re.search(r"return true;[^\n]*(fail safe|default)",
                                  text, re.IGNORECASE),
                        "unset preference must fail safe to reduced motion")

    def test_animation_duration_has_one_zero_when_reduced_policy(self):
        self.assertTrue(self.policy, "ReducedMotionPolicy.h is missing")
        self.assertIn("inline int duration(int nominalMs, bool isReduced)",
                      self.policy)
        self.assertIn("nominalMs <= 0", self.policy)
        self.assertIn("return isReduced ? 0 : nominalMs", self.policy)

    def test_qml_animations_get_the_policy_through_one_context_property(self):
        for marker in (
            '#include "ReducedMotionPolicy.h"',
            "class ReducedMotionBridge final : public QObject",
            "Q_INVOKABLE int duration(int nominalMs) const",
            "Q_PROPERTY(bool reduced READ reduced NOTIFY reducedChanged)",
            'QStringLiteral("canopyReducedMotion")',
            "&SettingsPreferencesBridge::preferenceChanged",
            "canopyReducedMotion::nativePreference()",
        ):
            with self.subTest(marker=marker):
                self.assertTrue(marker in self.main, "bridge marker missing: " + marker)

    def test_frozen_qml_declares_no_new_animation_machinery(self):
        qml_files = sorted(CLASSIC.glob("*.qml"))
        self.assertGreater(len(qml_files), 10)
        for path in qml_files:
            text = source(path)
            for token in FORBIDDEN_ANIMATIONS:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
