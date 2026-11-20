"""Guard exactly what is sourced and what remains an unapproved candidate.

Visual review is still required: these tests prevent identity drift, not taste.
"""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
NS = "{http://www.w3.org/2000/svg}"
MOODBOARD_ORDER = ["Files", "Browser", "Settings",
                   "Photos", "Terminal", "Trash"]


class ReferenceIdentityTests(unittest.TestCase):
    def test_launcher_is_white_reference_trace_with_three_cutouts(self):
        src = (CLASSIC / "assets/brand/penguin-launcher.svg")
        tree = ET.parse(src)
        root = tree.getroot()
        paths = list(root.iter(NS + "path"))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].get("fill"), "#fff")
        self.assertEqual(paths[0].get("fill-rule"), "evenodd")
        self.assertEqual(len(re.findall(r"\bM\s", paths[0].get("d", ""))), 4)
        self.assertEqual(len(list(root.iter(NS + "linearGradient"))), 0)
        self.assertIn("archived Minimalist White Penguin Silhouette.png",
                      (CLASSIC / "assets/brand/penguin-launcher.svg").read_text())

    def test_six_reference_categories_with_no_invented_composite(self):
        desktop = (CLASSIC / "Main.qml").read_text()
        dock = desktop.split('id: dockRow', 1)[1]
        names = re.findall(r'\{ title: "([^"]+)" \}', dock)
        self.assertEqual(names, MOODBOARD_ORDER)
        self.assertNotIn("Canopy", names)
        self.assertFalse((CLASSIC / "assets/icons/canopy.svg").exists())
        self.assertIn("assets/brand/penguin-launcher.svg", desktop)

    def test_sourced_launcher_has_charcoal_contrast(self):
        theme = (CLASSIC / "Theme.qml").read_text()
        self.assertIn('chrome: "#ed1f2326"', theme)
        self.assertIn('dockSurface: "#d91f2326"', theme)
        self.assertIn('color: "#f7f5eb"', (CLASSIC / "Main.qml").read_text())

    def test_gallery_depicts_landscape_not_unrelated_flower(self):
        gallery = (CLASSIC / "assets/icons/photos.svg").read_text()
        self.assertIn("landscape gallery artwork", gallery)
        self.assertIn("#175a45", gallery)
        self.assertNotIn("shutter pattern", gallery)

    def test_provenance_is_explicit_about_uncertainty(self):
        manifest = (ROOT / "docs/VISUAL_REFERENCE_PROVENANCE.md").read_text()
        self.assertIn("6bc6fbf22a8da5f20af4b6f35ec6647db80923d96480d831190d6159282724f", manifest)
        self.assertIn("not proof these are individually approved master assets", manifest)
        self.assertIn("not a byte-identical image", manifest)


if __name__ == "__main__":
    unittest.main()
