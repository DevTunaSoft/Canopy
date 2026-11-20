"""Validation for original Canopy SVG source assets; no image or visual approval implied."""
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "prototype" / "classic" / "assets" / "icons"
SAMPLES = ("browser", "files", "mail", "terminal")

class IconSourceTests(unittest.TestCase):
    def test_core_svg_sources_are_parseable(self):
        for icon in SAMPLES:
            with self.subTest(icon=icon):
                root = ET.parse(ICONS / f"{icon}.svg").getroot()
                self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
                self.assertEqual(root.attrib.get("viewBox"), "0 0 128 128")
                self.assertIn(icon.lower(), root.attrib.get("aria-label", "").lower())

    def test_icons_are_self_contained_and_size_bounded(self):
        for icon in SAMPLES:
            with self.subTest(icon=icon):
                data = (ICONS / f"{icon}.svg").read_text()
                self.assertLess(len(data), 10000)
                self.assertNotIn("<script", data.lower())
                self.assertNotIn("<image", data.lower())
                self.assertNotIn("http://", data.replace("http://www.w3.org/2000/svg", ""))
                self.assertNotIn("https://", data)
                self.assertNotIn("xlink:href", data)
                self.assertNotIn("filter=", data)

if __name__ == "__main__":
    unittest.main()
