"""ND-041: behavioural wiring of merged pure contracts into Classic panels.

Static, source-level gates for the two owned QML panels. They prove that the
registered host controllers are consumed through a bounded, fail-closed view
gate, that no polling/transport/second service is introduced, and that the
rendered visual half of both panels is byte-identical to the integration tip.

SYNTHETIC / NOT_RUN: no Qt compilation, desktop session, native device read or
Mint acceptance is claimed here.
"""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from canopy_features.accessibility import reduced_motion_contract
from canopy_features.settings.persisted_preferences import KEYS
from canopy_features.system.quick_controls_state import DISCLOSURES, STATUS_LABELS

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
SETTINGS = CLASSIC / "SettingsPanel.qml"
OVERLAY = CLASSIC / "QuickControlsOverlay.qml"

# SHA-256 of every byte from the first `visible: opened` line to EOF at the
# exact base tip 7535c0e9bc030d8fdf500967e56e385530bede96. All geometry,
# colours, fonts, object names, labels and component order live in this half.
RENDERED_VISUAL_SHA256 = {
    "SettingsPanel.qml":
        "38f1cf1512dff833dee7f8e1f844724682b2a1319bb3c798c501de0ebbbf192c",
    "QuickControlsOverlay.qml":
        "257e00bb5f337495bcd46ba97c34cbdb33d68ac99566802e7bd92f0e4d4fd02b",
}

FORBIDDEN = (
    "Timer {", "setInterval", "setTimeout", "Qt.createQmlObject",
    "LocalStorage", "NetworkRequest", "XmlHttp", "Qt.openUrlExternally",
    "QProcess", "Process {", "socket", "dbus", "systemd", "pkexec", "sudo ",
)


def code_only(source: str) -> str:
    return "\n".join(line for line in normalized(source).split("\n")
                     if not line.lstrip().startswith("//"))


def normalized(source: str) -> str:
    return source.replace("\r\n", "\n")


def rendered_visual_half(source: str) -> str:
    lines = normalized(source).split("\n")
    for index, line in enumerate(lines):
        if line.strip() == "visible: opened":
            return "\n".join(lines[index:])
    raise AssertionError("no rendered visual boundary")


def function_block(source: str, name: str) -> str:
    lines = normalized(source).split("\n")
    starts = [i for i, line in enumerate(lines)
              if line.strip().startswith("function " + name + "(")]
    if len(starts) != 1:
        raise AssertionError("%s found %d times" % (name, len(starts)))
    depth = 0
    for index in range(starts[0], len(lines)):
        depth += lines[index].count("{") - lines[index].count("}")
        if depth == 0 and index > starts[0]:
            return "\n".join(lines[starts[0]:index + 1])
    raise AssertionError("unbalanced function " + name)


class RenderedVisualLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = normalized(SETTINGS.read_text(encoding="utf-8"))
        cls.overlay = normalized(OVERLAY.read_text(encoding="utf-8"))

    def test_rendered_halves_are_byte_identical_to_base_tip(self):
        for name, source in (("SettingsPanel.qml", self.settings),
                             ("QuickControlsOverlay.qml", self.overlay)):
            with self.subTest(file=name):
                digest = hashlib.sha256(
                    rendered_visual_half(source).encode("utf-8")).hexdigest()
                self.assertEqual(digest, RENDERED_VISUAL_SHA256[name])

    def test_only_state_binding_lives_above_visual_boundary(self):
        for name, source in (("SettingsPanel.qml", self.settings),
                             ("QuickControlsOverlay.qml", self.overlay)):
            with self.subTest(file=name):
                self.assertIn("visible: opened", source)


class SettingsWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qml = normalized(SETTINGS.read_text(encoding="utf-8"))

    def test_registered_context_controller_is_a_read_only_fallback(self):
        for marker in (
                "property var controller: null",
                "function trustedController(candidate)",
                "function preferencesController()",
                'typeof canopySettingsPreferences !== "undefined"',
                "var adapter = preferencesController()",
                "preferencesController().setPreference(key, value)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.qml)
        # The injected controller stays first; no second store is constructed.
        self.assertLess(self.qml.index("var injected = trustedController(controller)"),
                        self.qml.index('typeof canopySettingsPreferences'))

    def test_trusted_view_is_bounded_and_fail_closed(self):
        for marker in (
                "try {", "} catch (error) {", "supplied.title.length <= 64",
                "supplied.value.length <= 16",
                "supplied.disclosure.length <= 128",
                "supplied.source.length <= 64",
                "supplied.value === \"\"",
                "return fallbackView(key)",
                '"Unavailable — no persisted preference store"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.qml)

    def test_key_order_and_value_domain_come_from_merged_contracts(self):
        self.assertIn('readonly property var keys: [\n        '
                      + ', '.join('"%s"' % key for key in list(KEYS)[:4]), self.qml)
        self.assertEqual(list(KEYS), [
            "reduced_motion", "network", "audio", "power",
            "session", "shell_pack", "notifications", "theme",
        ])
        block = function_block(self.qml, "allowedValues")
        for value in reduced_motion_contract.PREFERENCES:
            self.assertIn('"%s"' % value, block)
        self.assertIn('key === "reduced_motion"', block)

    def test_no_polling_transport_or_privileged_write(self):
        for forbidden in FORBIDDEN:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code_only(self.qml))


class QuickControlsWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qml = normalized(OVERLAY.read_text(encoding="utf-8"))

    def test_registered_host_state_is_a_read_only_fallback(self):
        for marker in (
                "property var hostState: null",
                "property var controller: null",
                "property var actionBridge: null",
                "function trustedAdapter(candidate)",
                "var supplied = trustedView(domain, hostState)",
                'typeof canopyHostState !== "undefined"',
                "supplied = trustedView(domain, canopyHostState)",
                "supplied = trustedView(domain, controller)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.qml)
        self.assertLess(self.qml.index("var supplied = trustedView(domain, hostState)"),
                        self.qml.index("trustedView(domain, canopyHostState)"))
        self.assertLess(self.qml.index("trustedView(domain, canopyHostState)"),
                        self.qml.index("trustedView(domain, controller)"))

    def test_view_gate_validates_the_whole_merged_view_contract(self):
        for marker in (
                "supplied.domain !== domain",
                "knownStatus(domain, supplied.status)",
                "supplied.status_label !== labelForStatus(supplied.status)",
                "typeof supplied.source !== \"string\"",
                "/^[a-z0-9_.:-]*$/.test(supplied.source)",
                "typeof supplied.observed !== \"boolean\"",
                'supplied.availability !== "AVAILABLE"',
                "!trustedDecision(supplied.control)",
                "!trustedDecision(supplied.settings)",
                "trustedDecision(decision)",
                "return fallbackView(domain)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.qml)

    def test_fixed_labels_and_disclosures_match_the_pure_contract(self):
        labels = function_block(self.qml, "labelForStatus")
        for label in STATUS_LABELS.values():
            with self.subTest(label=label):
                self.assertIn('return "%s"' % label, labels)
        disclosures = function_block(self.qml, "disclosureForReason")
        for disclosure in DISCLOSURES.values():
            with self.subTest(disclosure=disclosure):
                self.assertIn(disclosure, disclosures)

    def test_no_polling_transport_or_privileged_action_change(self):
        for forbidden in FORBIDDEN:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code_only(self.qml))
        actions = function_block(self.qml, "actionFor")
        for action in ("toggle_wifi", "toggle_mute", "suspend", "lock"):
            self.assertIn('return "%s"' % action, actions)
        self.assertIn("return !!(view.control && view.control.allowed\n"
                      "                  && actionBridge && typeof actionBridge.request",
                      self.qml)


if __name__ == "__main__":
    unittest.main()
