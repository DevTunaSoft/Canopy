"""Protect the settled Classic dock while launcher visual work continues.

Pin the baseline dock QML block and entire DockTile/asset manifest bytes
from the owner's previous settled Classic launcher branch. Any future
intentional dock change requires explicit approval and a new snapshot.
These checks supplement, not replace, real same-binary Qt pixel diff.
"""
import hashlib
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
APPROVED_DOCK_FNV64 = 0x4ac162b6d0fd5d40
DOCK_TILE_GIT_BLOB_SHA1 = "07dbf4f447eb0a67f8df5e15948d40559539cc6e"
APPROVED_MANIFEST_GIT_BLOB_SHA1 = "b120dc891a614ddbc5ef863514424112c02efee6"


def git_blob_sha1(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode() +
                        b"\0" + content).hexdigest()


def fnv1a64(content):
    digest = 0xcbf29ce484222325
    for byte in content:
        digest = ((digest ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return digest


class FrozenClassicDockTests(unittest.TestCase):
    def test_existing_dock_source_bytes_locked(self):
        # Read the committed blob, not the working-tree bytes: core.autocrlf
        # may convert line endings on Windows without changing the asset.
        def committed(relative):
            return subprocess.check_output(
                ["git", "-C", str(ROOT), "show", "HEAD:" + relative])

        tile = committed("prototype/classic/DockTile.qml")
        manifest = committed("prototype/classic/assets/approved/manifest.json")
        self.assertEqual(git_blob_sha1(tile), DOCK_TILE_GIT_BLOB_SHA1)
        self.assertEqual(git_blob_sha1(manifest),
                         APPROVED_MANIFEST_GIT_BLOB_SHA1)

    def test_dock_main_qml_geometry_and_behavior_locked(self):
        source = (CLASSIC / "Main.qml").read_text(encoding="utf-8")
        start = source.index("    Rectangle {\n        id: dock")
        # The dock is the final child in this approved Main.qml. Include
        # the final root brace in the frozen fingerprint; only the trailing
        # newline is excluded to match the reviewed baseline snapshot.
        self.assertTrue(source.endswith("\n}\n"))
        dock = source[start:-1]
        self.assertEqual(fnv1a64(dock.encode("ascii")),
                         APPROVED_DOCK_FNV64)
        self.assertNotIn("visible: !appLauncher.opened", source)

    def test_dock_renderer_stays_original_even_when_launcher_review_on(self):
        cpp = (CLASSIC / "main.cpp").read_text(encoding="utf-8")
        overlay = (CLASSIC / "LauncherOverlay.qml").read_text(encoding="utf-8")
        tile = (CLASSIC / "DockTile.qml").read_text(encoding="utf-8")
        self.assertIn("approvedRoot, terminalCandidatePath, false, &roundedError",
                      cpp)
        self.assertIn("approvedRoot, terminalCandidatePath, true, &reviewError",
                      cpp)
        self.assertIn('QStringLiteral("canopy-dock"), roundedIcons', cpp)
        self.assertIn('QStringLiteral("canopy-launcher-review")', cpp)
        self.assertIn('"image://canopy-dock/" + iconName.toLowerCase()', tile)
        self.assertIn('"image://canopy-launcher-review/"', overlay)
        self.assertIn('framingReviewMode: canopyIconFramingReview',
                      (CLASSIC / "Main.qml").read_text(encoding="utf-8"))

    def test_regression_checker_rejects_single_changed_dock_pixel(self):
        source = (ROOT / "tools/check_classic_icon_frame_diff.py").read_text()
        self.assertIn('if scene == "desktop":', source)
        self.assertIn("if orig != modified:", source)
        self.assertIn("frozen dock/desktop pixel changed", source)
        self.assertIn('if min(counts) == 0:', source)

    def test_actual_qt_geometry_not_just_catalogue_name_checked(self):
        source = (CLASSIC / "main.cpp").read_text()
        overlay = (CLASSIC / "LauncherOverlay.qml").read_text()
        self.assertIn("launcherButtonImagesAreCentered(applicationLauncher", source)
        self.assertIn("SELF_TEST_FAIL: launcher icon not centered", source)
        self.assertIn('objectName: "canopyLauncherAppButton"', overlay)
        self.assertIn('objectName: "canopyLauncherIcon"', overlay)
        self.assertIn("qAbs(imageMidX - item->width() / 2) > 0.75", source)


if __name__ == "__main__":
    unittest.main()
