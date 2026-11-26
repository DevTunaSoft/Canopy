"""Targeted PE-037 regression test for the Classic dock tooltip binding.

Pure text-level gate: no Qt, X11, Mint, screen reader, build or VM is used.
The required runtime verification (real Tab focus + AT-SPI tooltip) remains
NOT_RUN; this test only proves the QML binding exposes focus.

PE-037 owns exactly one QA005-003 site in this change: DockTile.qml.
LauncherOverlay.qml and PreviewWindow.qml are owned by other open PRs.
"""
import os
from pathlib import Path
import unittest

from canopy_features.accessibility import tooltip_focus_contract as contract


ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DOCK = ROOT / "prototype" / "classic" / "DockTile.qml"
DOCK = Path(os.environ.get("PE037_DOCKTILE_PATH", str(_DEFAULT_DOCK)))

EXPECTED_BINDING = "    ToolTip.visible: tile.hovered || tile.activeFocus"
HOVER_ONLY_BINDING = "    ToolTip.visible: hovered"

# Frozen appearance/string lines copied from the exact base blob at c6de241.
# The visual lock forbids changing these in an accessibility-only fix.
FROZEN_LINES = (
    '    objectName: "canopyDockTile"',
    "    width: 58",
    "    height: 70",
    "    implicitWidth: 58",
    "    implicitHeight: 70",
    "    padding: 0",
    "    hoverEnabled: true",
    '    Accessible.name: iconName + " preview"',
    '    Accessible.description: "Original demonstration artwork, not a working app launcher"',
    '    ToolTip.text: iconName === "Files" ? "Toggle Files preview" : iconName + " — preview only"',
    "            width: 56",
    "            height: 56",
    "            radius: 16",
    "            visible: tile.hovered || tile.activeFocus",
    '            color: tile.hovered ? "#30ffffff" : "#18ffffff"',
    '            border.color: tile.activeFocus ? "#aac9f2ff" : "transparent"',
    "            border.width: tile.activeFocus ? 2 : 0",
)


class DockTooltipFocusTests(unittest.TestCase):
    def test_dock_tip_visible_on_keyboard_focus(self):
        text = DOCK.read_text(encoding="utf-8")
        self.assertEqual(text.count(EXPECTED_BINDING), 1)
        self.assertNotIn(HOVER_ONLY_BINDING, text)
        # The reference pattern at Main.qml:122 uses hovered || activeFocus.
        self.assertEqual(
            contract.INTENDED_QML_BINDING,
            "ToolTip.visible: hovered || activeFocus",
        )

    def test_binding_matches_focus_contract_semantics(self):
        focus_only = contract.TooltipInput(hovered=False, active_focus=True)
        result = contract.describe_tooltip(
            focus_only, accessible_name="Files preview")
        self.assertTrue(result.visible)
        self.assertTrue(result.via_keyboard)
        self.assertFalse(result.via_pointer)
        lost_focus = contract.TooltipInput(hovered=False, active_focus=False)
        self.assertFalse(contract.tooltip_visible(lost_focus))

    def test_visual_lock_lines_are_unchanged(self):
        text = DOCK.read_text(encoding="utf-8")
        for line in FROZEN_LINES:
            with self.subTest(line=line):
                self.assertEqual(text.count(line), 1)


if __name__ == "__main__":
    unittest.main()
