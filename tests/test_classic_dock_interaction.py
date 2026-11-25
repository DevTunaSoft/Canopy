"""Deterministic interaction-state audit for the frozen Classic dock.

This module verifies, from the pinned Qt source and the compiled self-test
contract, that the dock's hover, press-to-activation, keyboard focus,
activity indicator and accessible names are wired through state that already
exists. It deliberately changes no QML, asset, geometry or daemon: the Classic
dock and DockTile are byte-frozen by ``test_classic_dock_frozen`` and
``test_classic_window_activation_host``. A green run is a source-contract
audit, NOT compiled Qt evidence, NOT screen-reader verification and NOT Linux
Mint acceptance.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(os.environ.get(
    "CANOPY_DOCK_INTERACTION_ROOT", str(Path(__file__).resolve().parents[1])))
CLASSIC = ROOT / "prototype" / "classic"
DOCK_TILE = CLASSIC / "DockTile.qml"
MAIN_QML = CLASSIC / "Main.qml"
MAIN_CPP = CLASSIC / "main.cpp"

sys.path.insert(0, str(ROOT / "tests"))
from test_classic_dock_frozen import (  # noqa: E402
    APPROVED_DOCK_FNV64,
    DOCK_TILE_GIT_BLOB_SHA1,
    fnv1a64,
    git_blob_sha1,
)
from tools.qa import classic_keyboard_accessibility_gate as gate  # noqa: E402


def _text(path: Path) -> str:
    """Read source with universal newline handling (Windows checkouts)."""
    return path.read_text(encoding="utf-8")


class ClassicDockInteractionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tile = _text(DOCK_TILE)
        cls.main = _text(MAIN_QML)
        cls.cpp = _text(MAIN_CPP)

    def test_button_hover_and_click_activation_are_explicit(self):
        # Button supplies `pressed`; the tile opts into hover tracking and
        # forwards the release as the single frozen activation signal.
        for needle in ("import QtQuick.Controls", "Button {",
                       "hoverEnabled: true",
                       "signal activated(string applicationName)",
                       "onClicked: tile.activated(tile.iconName)"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.tile)

    def test_hover_halo_uses_only_existing_tile_state(self):
        for needle in ("background: Item {",
                       "visible: tile.hovered || tile.activeFocus",
                       'color: tile.hovered ? "#30ffffff" : "#18ffffff"'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.tile)
        for forbidden in ("Timer {", "NumberAnimation", "ShaderEffect"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.tile)

    def test_compiled_click_fixture_proves_press_to_activation_path(self):
        for needle in (
                'QMetaObject::invokeMethod(filesTile, "clicked", '
                'Qt::DirectConnection)',
                "SELF_TEST_FAIL: Files dock did not hide preview",
                "SELF_TEST_FAIL: Files dock did not restore preview",
                "SELF_TEST_PASS: Files dock hide/restore and activity indicator"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.cpp)

    def test_keyboard_focus_border_matches_pinned_gate_details(self):
        for needle in (
                'border.color: tile.activeFocus ? "#aac9f2ff" : "transparent"',
                "border.width: tile.activeFocus ? 2 : 0"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.tile)
        gate_details = {step_id: detail for step_id, _key, detail in gate.STEPS}
        self.assertEqual(gate_details["dock_tab_focus"], {
            "focus": "canopyDockTile",
            "accessible_name": "Files preview",
            "border_width": "2",
        })
        self.assertEqual(gate_details["dock_arrow_next"], {
            "focus": "canopyDockTile",
            "accessible_name": "Browser preview",
            "border_width": "2",
        })

    def test_tooltip_binding_is_present_on_hover(self):
        # Focus disclosure is provided by the halo border and accessible
        # name; adding focus to the tooltip would edit frozen visual QML and
        # is outside this verification-only change.
        for needle in ("ToolTip.visible: hovered",
                       'ToolTip.text: iconName === "Files" ? '
                       '"Toggle Files preview" : iconName + " — preview only"'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.tile)

    def test_active_app_indicator_follows_existing_preview_state(self):
        for source, needle in (
                (self.main, 'previewActive: modelData.title === "Files" '
                            '&& filesPreview.visible'),
                (self.main, "filesPreview.visible = !filesPreview.visible"),
                (self.tile, "visible: tile.previewActive")):
            with self.subTest(needle=needle):
                self.assertIn(needle, source)

    def test_host_applies_trusted_window_state_to_dock_tiles(self):
        for needle in (
                'setTileProperty(tile, QStringLiteral("windowRunning"), running)',
                'setTileProperty(tile, QStringLiteral("windowActive"), active)',
                'setTileProperty(tile, QStringLiteral("activationIntent"), intent)',
                'QQmlProperty accessibleDescription(',
                'QStringLiteral(" active window")'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.cpp)
        self.assertIn('canopyWindowActivationState', _text(
            CLASSIC / "WindowActivationIndicators.qml"))

    def test_accessible_names_are_bound_to_icon_name(self):
        for needle in (
                'Accessible.name: iconName + " preview"',
                'Accessible.description: "Original demonstration artwork, '
                'not a working app launcher"',
                'Accessible.name: tile.iconName + " original dock artwork"'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.tile)

    def test_interaction_audit_does_not_touch_frozen_visual_bytes(self):
        tile_bytes = DOCK_TILE.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(git_blob_sha1(tile_bytes), DOCK_TILE_GIT_BLOB_SHA1)
        start = self.main.index("    Rectangle {\n        id: dock")
        self.assertEqual(fnv1a64(self.main[start:-1].encode("ascii")),
                         APPROVED_DOCK_FNV64)

    def test_no_new_background_service_is_introduced(self):
        for forbidden in ("QProcess", "socket", "Thread(", "while True"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.tile)
                self.assertNotIn(forbidden, self.main)


if __name__ == "__main__":
    unittest.main()
