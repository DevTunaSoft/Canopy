"""Security and completeness controls for the original dock icon asset family."""
from pathlib import Path
import tempfile
import unittest

from tools.check_icon_set import ICON_NAMES, verify_icon, verify_icon_set

ICONS = (Path(__file__).resolve().parents[1] /
         "prototype/classic/assets/icons")
BRAND = ICONS.parent / "brand" / "penguin-launcher.svg"


class IconSourceTests(unittest.TestCase):
    def test_seven_icons_match_declared_set(self):
        verify_icon_set(ICONS)
        self.assertEqual(len(ICON_NAMES), 7)

    def check_reject(self, changed_svg, message):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "icon.svg"
            path.write_text(changed_svg, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, message):
                verify_icon(path)

    def test_original_launcher_is_verified(self):
        verify_icon(BRAND)
        text = BRAND.read_text(encoding="utf-8")
        self.assertIn("Canopy penguin launcher symbol", text)
        self.assertNotIn("<image", text)
        self.assertNotIn("<script", text)

    def test_corrupt_launcher_is_rejected(self):
        source = BRAND.read_text(encoding="utf-8")
        self.check_reject(source.replace("</svg>", "<script>bad()</script></svg>"),
                          "Unsupported or unsafe")

    def test_no_svg_script_allowed(self):
        source = (ICONS / "files.svg").read_text(encoding="utf-8")
        self.check_reject(source.replace("</svg>", "<script>bad()</script></svg>"),
                          "Unsupported or unsafe")

    def test_external_reference_not_allowed(self):
        source = (ICONS / "files.svg").read_text(encoding="utf-8")
        self.check_reject(source.replace("<path ", '<path href="https://invalid.example/icon" ', 1),
                          "Unsupported icon attribute")

    def test_broken_gradient_not_allowed(self):
        source = (ICONS / "canopy.svg").read_text(encoding="utf-8")
        self.check_reject(source.replace("url(#bg)", "url(#notthere)", 1),
                          "undefined gradient")

    def test_missing_asset_fails_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            for name in ICON_NAMES[:-1]:
                (destination / f"{name}.svg").write_bytes((ICONS / f"{name}.svg").read_bytes())
            with self.assertRaisesRegex(ValueError, "Expected exactly seven"):
                verify_icon_set(destination)


if __name__ == "__main__":
    unittest.main()
