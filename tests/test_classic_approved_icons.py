"""Regression contracts for user-approved Canopy Classic visual choices.

Selections refer to reference artwork only; do not accidentally treat draft SVGs
as the approved icons or claim that production icon resources are installed.
"""
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "prototype" / "classic" / "assets" / "icons" / "classic-approved-selections.json"
APPROVED = {
    "browser": 3,
    "mail": 5,
    "files": 2,
    "calendar": 3,
    "photos": 2,
    "music": 3,
    "terminal": 4,
    "settings": 8,
}


class ApprovedClassicSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_version_and_approval_scope(self):
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(self.manifest["style"], "classic")
        self.assertEqual(
            self.manifest["selection_state"], "user_approved_visual_reference"
        )

    def test_all_eight_choices_are_exact_and_nonduplicated(self):
        entries = self.manifest["icons"]
        apps = [entry["app"] for entry in entries]
        self.assertEqual(len(apps), 8)
        self.assertEqual(len(set(apps)), 8)
        self.assertEqual(
            {entry["app"]: entry["option"] for entry in entries},
            APPROVED,
        )

    def test_qt_dock_and_launcher_share_exactly_the_approved_catalog(self):
        classic = ROOT / "prototype" / "classic"
        main = (classic / "Main.qml").read_text(encoding="utf-8")
        launcher = (classic / "LauncherOverlay.qml").read_text(encoding="utf-8")
        # Restrict matches to the declarative catalog block, not comments or
        # symbols used elsewhere in the presentation.
        start = main.index("readonly property var classicApps: [")
        end = main.index("]", start)
        catalog = main[start:end]
        shown = re.findall(
            r'\\{ name: "([A-Za-z]+)", icon: "([A-Za-z]+)" \\}',
            catalog,
        )
        expected = [item["app"].title() for item in self.manifest["icons"]]
        self.assertEqual([name for name, _ in shown], expected)
        self.assertEqual([icon for _, icon in shown], expected)
        self.assertIn("model: root.classicApps", main)
        self.assertIn("applications: root.classicApps", main)
        self.assertIn("model: launcher.filteredApps", launcher)
        self.assertNotIn("readonly property var applications: [", launcher)

    def test_no_selected_concept_is_misrepresented_as_shipped_asset(self):
        for entry in self.manifest["icons"]:
            with self.subTest(app=entry["app"]):
                self.assertGreaterEqual(entry["option"], 1)
                self.assertLessEqual(entry["option"], 8)
                self.assertTrue(entry["description"].strip())
                self.assertIsNone(entry["production_asset"])


if __name__ == "__main__":
    unittest.main()
