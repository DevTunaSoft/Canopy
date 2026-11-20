"""Security and source-contract regression tests for original vector artwork."""
import tempfile
import unittest
from pathlib import Path

from tools.check_art_asset import verify_artwork

ART = (Path(__file__).resolve().parents[1] /
       "prototype/classic/assets/wallpapers/blue-current.svg")


class OriginalArtworkTests(unittest.TestCase):
    def setUp(self):
        self.source = ART.read_text(encoding="utf-8")

    def check_rejection(self, source: str, error: str):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "fixture.svg"
            candidate.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, error):
                verify_artwork(candidate)

    def test_original_artwork_is_self_contained(self):
        verify_artwork(ART)

    def test_refuses_external_resources(self):
        self.check_rejection(
            self.source.replace('<rect width="1920"', '<rect href="https://evil.invalid/x" width="1920"', 1),
            "Forbidden SVG attribute",
        )

    def test_refuses_script_elements(self):
        self.check_rejection(
            self.source.replace("</svg>", "<script>alert('x')</script></svg>"),
            "Forbidden SVG element",
        )

    def test_refuses_doctype(self):
        self.check_rejection(
            self.source.replace("<svg ", '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///tmp/x">]><svg ', 1),
            "External entities",
        )

    def test_refuses_missing_gradient(self):
        self.check_rejection(
            self.source.replace("url(#sky)", "url(#missing)", 1),
            "Gradient references",
        )

    def test_refuses_wrong_aspect_ratio(self):
        self.check_rejection(
            self.source.replace('viewBox="0 0 1920 1080"', 'viewBox="0 0 1920 1200"', 1),
            "1920x1080",
        )

    def test_refuses_unsupported_filters(self):
        self.check_rejection(
            self.source.replace("</svg>", '<filter id="evil"/></svg>'),
            "Forbidden SVG element",
        )


if __name__ == "__main__":
    unittest.main()
