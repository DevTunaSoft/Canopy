import tempfile
from pathlib import Path
import unittest
from scripts.readonly_syntax_check import validate_sources
from scripts.mint_testlab import COMMANDS


class ReadOnlySyntaxTests(unittest.TestCase):
    def test_syntax_command_does_not_use_compileall(self):
        self.assertNotIn("compileall", COMMANDS["syntax"])
        self.assertEqual(COMMANDS["syntax"][1], "-B")

    def test_valid_sources_do_not_create_pycache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for directory in ("canopy", "tests", "scripts"):
                path = root / directory
                path.mkdir()
                (path / "valid.py").write_text("x = 1\n")
            self.assertEqual(validate_sources(root)["status"], "PASS")
            self.assertFalse(list(root.rglob("__pycache__")))

    def test_invalid_syntax_is_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for directory in ("canopy", "tests", "scripts"):
                (root / directory).mkdir()
            (root / "canopy" / "bad.py").write_text("def broken(:\n")
            self.assertEqual(validate_sources(root)["status"], "FAIL")

    def test_missing_directory_blocks_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(validate_sources(folder)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
