"""Lightweight source contract tests; not Qt runtime tests."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"

class ClassicSourceTests(unittest.TestCase):
    def test_required_files(self):
        for name in ("CMakeLists.txt", "main.cpp", "Main.qml", "README.md"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())

    def test_explicit_nonproduction_scope(self):
        self.assertIn("not a Linux desktop session", (ROOT / "README.md").read_text())
        self.assertIn("Qt6::Quick", (ROOT / "CMakeLists.txt").read_text())
        self.assertIn("ApplicationWindow", (ROOT / "Main.qml").read_text())

if __name__ == "__main__":
    unittest.main()
