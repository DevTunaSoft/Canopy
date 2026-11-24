"""Regression: foundation PASS must not be produced by links that escape the repo.

The CLI prints ``PASS: foundation files, tagline, and local Markdown links``.
A required document that links to a host-absolute file, to a path reached by
``..`` above the repository root, or through a symlink to such a file must
therefore be reported as a broken relative link instead of producing a false
PASS.
"""
import tempfile
import unittest
from pathlib import Path

from tools.check_foundation import REQUIRED, validate


class FoundationLinkScopeTests(unittest.TestCase):
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
        self.architecture = self.root / "docs" / "ARCHITECTURE.md"

    @staticmethod
    def _broken(errors):
        return [e for e in errors if e.startswith("Broken relative link")]

    def test_absolute_host_path_link_is_rejected(self):
        # A host-absolute target replaces the repo-relative parent entirely.
        target = Path(__file__).resolve().as_posix()
        self.architecture.write_text(f"[host]({target})\n", encoding="utf-8")
        self.assertTrue(self._broken(validate(self.root)))

    def test_parent_traversal_escape_is_rejected(self):
        # Sibling of the temp repo root: reachable by two '..' segments.
        outside = self.root.parent / (self.root.name + "-outside.txt")
        outside.write_text("outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        self.architecture.write_text(
            f"[esc](../../{outside.name})\n", encoding="utf-8")
        self.assertTrue(self._broken(validate(self.root)))

    def test_symlink_escape_is_rejected(self):
        outside = self.root.parent / (self.root.name + "-symlink-target.txt")
        outside.write_text("outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        link = self.root / "docs" / "host-link.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("filesystem does not allow creating symlinks")
        self.architecture.write_text("[host](host-link.txt)\n", encoding="utf-8")
        self.assertTrue(self._broken(validate(self.root)))

    def test_in_repo_relative_link_still_valid(self):
        self.architecture.write_text("[roadmap](ROADMAP.md)\n", encoding="utf-8")
        self.assertEqual(validate(self.root), [])

    def test_parent_link_inside_root_still_valid(self):
        self.architecture.write_text("[readme](../README.md)\n", encoding="utf-8")
        self.assertEqual(validate(self.root), [])

    def test_external_link_still_skipped(self):
        self.architecture.write_text("[site](https://example.com/x)\n", encoding="utf-8")
        self.assertEqual(validate(self.root), [])

    def test_missing_link_still_reported(self):
        self.architecture.write_text("[x](missing.md)\n", encoding="utf-8")
        self.assertTrue(self._broken(validate(self.root)))


if __name__ == "__main__":
    unittest.main()
