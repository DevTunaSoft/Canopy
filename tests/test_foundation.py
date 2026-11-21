"""Regression tests for the Canopy foundation checker."""
import tempfile
import unittest
from pathlib import Path
from tools.check_foundation import REQUIRED, validate


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in REQUIRED:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Example\n", encoding="utf-8")
        (self.root / "README.md").write_text(
            "# Canopy\nThe Familiar Feel. The Freedom of Linux.\n",
            encoding="utf-8",
        )

    def test_valid_foundation(self):
        self.assertEqual(validate(self.root), [])

    def test_missing_file(self):
        (self.root / "AGENTS.md").unlink()
        self.assertTrue(any("Missing required file" in e for e in validate(self.root)))

    def test_broken_local_link(self):
        (self.root / "AGENTS.md").write_text("[missing](no-file.md)", encoding="utf-8")
        self.assertTrue(any("Broken relative link" in e for e in validate(self.root)))

    def test_valid_local_link(self):
        (self.root / "AGENTS.md").write_text("[roadmap](docs/ROADMAP.md)", encoding="utf-8")
        self.assertEqual(validate(self.root), [])

    def test_missing_tagline(self):
        (self.root / "README.md").write_text("# Canopy", encoding="utf-8")
        self.assertTrue(any("tagline" in e for e in validate(self.root)))


if __name__ == "__main__":
    unittest.main()
