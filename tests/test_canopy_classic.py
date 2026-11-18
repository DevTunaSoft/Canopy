"""Regression tests for the reversible Cinnamon Classic prototype."""
import tempfile
import unittest
from pathlib import Path

from tools.canopy_classic import LayoutError, build_layout, decode_strv, encode_strv, safe_save


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.applets = [
            "panel1:left:0:menu@cinnamon.org:0",
            "panel1:center:1:grouped-window-list@cinnamon.org:2",
            "panel1:right:0:network@cinnamon.org:5",
            "panel1:right:1:calendar@cinnamon.org:6",
        ]

    def test_layout_preserves_applets_and_instances(self):
        panels, applets = build_layout(["1:0:bottom"], self.applets)
        self.assertEqual(panels, ["1:0:top", "2:0:bottom"])
        self.assertEqual(len(applets), len(self.applets))
        self.assertEqual(applets[0], "panel1:left:0:menu@cinnamon.org:0")
        self.assertIn("panel2:center:0:grouped-window-list@cinnamon.org:2", applets)
        self.assertTrue(any(x.endswith("network@cinnamon.org:5") for x in applets))

    def test_refuses_complex_multimonitor(self):
        with self.assertRaises(LayoutError):
            build_layout(["1:0:bottom", "2:1:top"], self.applets)

    def test_requires_native_menu_and_grouped_list(self):
        with self.assertRaises(LayoutError):
            build_layout(["1:0:bottom"], self.applets[1:])

    def test_string_array_roundtrip(self):
        original = ["hello's", "spaces here", "á"]
        self.assertEqual(decode_strv(encode_strv(original)), original)
        with self.assertRaises(LayoutError):
            decode_strv('{"bad":"object"}')

    def test_backup_must_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved.json"
            safe_save(path, {"hello": "world"})
            self.assertTrue(path.exists())
            with self.assertRaises(LayoutError):
                safe_save(path, {"hello": "oops"})


if __name__ == "__main__":
    unittest.main()
