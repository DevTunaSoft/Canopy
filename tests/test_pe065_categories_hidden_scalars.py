"""PE-065 regression: category parsing must not launder hidden scalars.

``str.strip()`` silently removes C0 separators (0x1c-0x1f) and C1 NEL, so a
desktop-entry ``Categories=`` value containing them could be accepted as a
well-formed category id. The catalog ingest gate already refuses those
scalars; the public parser must agree instead of turning them into valid ids.
Pure offline unit test: no Qt, filesystem, process or polling.
"""
import unittest

from canopy_features.launcher.app_categories import CategoryError, parse_categories


class HiddenScalarCategoryTests(unittest.TestCase):
    def test_strip_cannot_launder_control_scalars_into_valid_ids(self):
        for raw in (
            "Game;\x1cUtility;",     # C0 file separator, stripped by str.strip()
            "Game;\x1fUtility;",     # C0 unit separator, stripped by str.strip()
            "Ga\x85me;",             # C1 NEL, stripped by str.strip()
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(CategoryError):
                    parse_categories(raw)

    def test_ordinary_ascii_spacing_and_empty_segments_still_parse(self):
        self.assertEqual(
            parse_categories(" Game ; Utility;; Network; "),
            ("Game", "Utility", "Network"),
        )


if __name__ == "__main__":
    unittest.main()
