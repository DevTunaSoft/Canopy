"""Offline unit tests for freedesktop icon-theme name resolution.

These tests use temporary directories only. They never touch the approved
artwork, a real desktop theme, a compiled Qt binary or a Linux Mint guest.
"""

import tempfile
import unittest
from pathlib import Path

from canopy_features.launcher.icon_theme_resolution import (
    LOCKED,
    MAX_INDEX_BYTES,
    MISSING,
    REJECTED,
    RESOLVED,
    IconThemeResolver,
    resolve_icon_name,
)


PNG = b"\x89PNG\r\n\x1a\nCANOPY-TEST"


def write_theme(base, name, directories=(), inherits=(), files=()):
    """Create a minimal freedesktop theme tree under <base>/icons/<name>."""
    root = base / "icons" / name
    root.mkdir(parents=True, exist_ok=True)
    index = "[Icon Theme]\nName=%s\n" % name
    if inherits:
        index += "Inherits=%s\n" % ",".join(inherits)
    if directories:
        index += "Directories=%s\n" % ",".join(directories)
    (root / "index.theme").write_text(index, encoding="utf-8")
    for directory in directories:
        (root / directory).mkdir(parents=True, exist_ok=True)
    for relative in files:
        item = root / relative
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_bytes(PNG)
    return root


class IconThemeResolutionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def resolver(self, **kwargs):
        kwargs.setdefault("data_home", self.base)
        kwargs.setdefault("data_dirs", ())
        return IconThemeResolver(**kwargs)

    # -- normal resolution ---------------------------------------------

    def test_resolves_png_from_theme(self):
        write_theme(self.base, "hicolor", ["48x48/apps"],
                    files=["48x48/apps/firefox.png"])
        result = self.resolver().resolve("firefox")
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.theme, "hicolor")
        self.assertEqual(result.path.name, "firefox.png")
        self.assertIn("theme icon resolved", result.reason)

    def test_extension_order_png_before_svg(self):
        write_theme(self.base, "hicolor", ["48x48/apps"], files=[
            "48x48/apps/thing.svg", "48x48/apps/thing.png"])
        result = self.resolver().resolve("thing")
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.path.suffix, ".png")

    def test_inherited_theme_resolution(self):
        write_theme(self.base, "hicolor")
        write_theme(self.base, "Base", ["48x48/apps"],
                    files=["48x48/apps/nemo.png"])
        write_theme(self.base, "Canopy", inherits=["Base"])
        result = self.resolver().resolve("nemo", theme="Canopy")
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.theme, "Base")
        self.assertIn("Base", result.searched)

    def test_implicit_hicolor_fallback(self):
        write_theme(self.base, "hicolor", ["48x48/apps"],
                    files=["48x48/apps/fallback.png"])
        write_theme(self.base, "Canopy")
        result = self.resolver().resolve("fallback", theme="Canopy")
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.theme, "hicolor")

    # -- missing icons --------------------------------------------------

    def test_missing_icon(self):
        write_theme(self.base, "hicolor", ["48x48/apps"],
                    files=["48x48/apps/other.png"])
        result = self.resolver().resolve("absent")
        self.assertEqual(result.status, MISSING)
        self.assertIsNone(result.path)
        self.assertIn("not found", result.reason)

    # -- path escape ----------------------------------------------------

    def test_relative_traversal_rejected(self):
        result = self.resolver().resolve("../secret")
        self.assertEqual(result.status, REJECTED)
        self.assertIn("unsafe icon name", result.reason)
        self.assertIsNone(result.path)

    def test_nested_path_in_name_rejected(self):
        result = self.resolver().resolve("apps/evil")
        self.assertEqual(result.status, REJECTED)
        self.assertIn("unsafe icon name", result.reason)

    def test_absolute_path_outside_roots_rejected(self):
        result = self.resolver().resolve("/etc/passwd")
        self.assertEqual(result.status, REJECTED)
        self.assertIn("outside allowed roots", result.reason)

    def test_absolute_path_inside_data_root_resolved(self):
        icon = self.base / "pixmaps" / "local.png"
        icon.parent.mkdir(parents=True, exist_ok=True)
        icon.write_bytes(PNG)
        result = self.resolver().resolve(str(icon))
        self.assertEqual(result.status, RESOLVED)
        self.assertEqual(result.path, icon)

    # -- cyclic inheritance --------------------------------------------

    def test_cyclic_inheritance_rejected(self):
        write_theme(self.base, "hicolor")
        write_theme(self.base, "A", inherits=["B"])
        write_theme(self.base, "B", inherits=["A"])
        result = self.resolver().resolve("anything", theme="A")
        self.assertEqual(result.status, REJECTED)
        self.assertIn("cyclic", result.reason)

    def test_self_inheritance_rejected(self):
        write_theme(self.base, "hicolor")
        write_theme(self.base, "Loop", inherits=["Loop"])
        result = self.resolver().resolve("anything", theme="Loop")
        self.assertEqual(result.status, REJECTED)
        self.assertIn("cyclic", result.reason)

    def test_inheritance_chain_is_bounded(self):
        write_theme(self.base, "hicolor")
        write_theme(self.base, "A", inherits=["B"])
        write_theme(self.base, "B", inherits=["C"])
        write_theme(self.base, "C")
        result = self.resolver(max_themes=2).resolve("anything", theme="A")
        self.assertEqual(result.status, REJECTED)
        self.assertIn("too many icon themes", result.reason)

    # -- locked assets --------------------------------------------------

    def test_locked_asset_not_replaced_by_theme(self):
        approved_root = self.base / "approved"
        approved_root.mkdir(parents=True, exist_ok=True)
        approved = approved_root / "Files.png"
        approved.write_bytes(b"APPROVED-MASTER")
        write_theme(self.base, "hicolor", ["48x48/apps"],
                    files=["48x48/apps/Files.png"])
        result = self.resolver(
            locked={"Files": approved}, approved_root=approved_root).resolve("Files")
        self.assertEqual(result.status, LOCKED)
        self.assertEqual(result.path, approved)
        self.assertNotEqual(result.path, self.base / "icons" / "hicolor" /
                            "48x48" / "apps" / "Files.png")
        self.assertIn("substitution refused", result.reason)

    def test_locked_asset_missing_fails_closed(self):
        write_theme(self.base, "hicolor", ["48x48/apps"],
                    files=["48x48/apps/Files.png"])
        missing = self.base / "approved" / "gone.png"
        result = self.resolver(locked={"Files": missing}).resolve("Files")
        self.assertEqual(result.status, REJECTED)
        self.assertIn("locked asset", result.reason)

    def test_locked_asset_outside_approved_root_rejected(self):
        approved_root = self.base / "approved"
        approved_root.mkdir(parents=True, exist_ok=True)
        elsewhere = self.base / "elsewhere.png"
        elsewhere.write_bytes(PNG)
        result = self.resolver(
            locked={"Files": elsewhere}, approved_root=approved_root).resolve("Files")
        self.assertEqual(result.status, REJECTED)

    # -- bounded, read-only behaviour ----------------------------------

    def test_oversized_index_is_never_used(self):
        root = write_theme(self.base, "hicolor", ["48x48/apps"],
                           files=["48x48/apps/big.png"])
        (root / "index.theme").write_bytes(b"x" * (MAX_INDEX_BYTES + 1))
        result = self.resolver().resolve("big")
        self.assertNotEqual(result.status, RESOLVED)

    def test_resolution_does_not_modify_index(self):
        root = write_theme(self.base, "hicolor", ["48x48/apps"],
                           files=["48x48/apps/firefox.png"])
        before = (root / "index.theme").read_bytes()
        self.resolver().resolve("firefox")
        self.assertEqual((root / "index.theme").read_bytes(), before)

    def test_convenience_wrapper(self):
        write_theme(self.base, "hicolor", ["48x48/apps"],
                    files=["48x48/apps/wrap.png"])
        result = resolve_icon_name("wrap", data_home=self.base, data_dirs=())
        self.assertEqual(result.status, RESOLVED)


if __name__ == "__main__":
    unittest.main()
