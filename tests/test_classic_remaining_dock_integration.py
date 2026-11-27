"""Source contracts for the remaining Classic dock app launches.

Calendar and Photos join Files, Browser and Mail on the single
host-owned GIO bridge. Terminal now has its own exact-label adapter with a
documented fallback; see ``test_classic_terminal_dock_native_launch``.
These are source-level invariants; the compiled
self-tests and isolated GIO fixtures are exercised by classic-qt CI. The
bridge accepts only one exact frozen dock label per instance and leaves every
approved QML/artwork byte untouched.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_classic_dock_frozen import (
    APPROVED_DOCK_FNV64,
    fnv1a64,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"
NAMES = ("Calendar", "Photos")
DESKTOP_IDS = {
    "Calendar": "org.gnome.Calendar.desktop",
    "Photos": "org.gnome.Loupe.desktop",
}


class ClassicRemainingDockIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = (SOURCE / "main.cpp").read_text(encoding="utf-8")
        cls.launcher_cpp = (SOURCE / "SystemAppLauncher.cpp").read_text(
            encoding="utf-8")
        cls.workflow = (ROOT / ".github" / "workflows" /
                        "classic-qt.yml").read_text(encoding="utf-8")

    def test_named_bridge_reuses_the_single_host_launcher(self):
        cpp = self.cpp
        self.assertIn("class RemainingDockLaunchBridge final : public QObject", cpp)
        self.assertIn('name == QStringLiteral("Calendar")', cpp)
        self.assertIn('name == QStringLiteral("Photos")', cpp)
        self.assertIn("name != m_name", cpp)
        self.assertIn("m_launcher.launch(name)", cpp)
        self.assertIn("CANOPY_REMAINING_DOCK_REJECTED", cpp)
        self.assertIn("CANOPY_REMAINING_DOCK_LAUNCH_REQUESTED", cpp)
        self.assertIn("CANOPY_REMAINING_DOCK_LAUNCH_REFUSED", cpp)
        for name in NAMES:
            with self.subTest(name=name):
                self.assertIn(f'QStringLiteral("{name}")', self.launcher_cpp)
                self.assertIn(f'QStringLiteral("{DESKTOP_IDS[name]}")',
                              self.launcher_cpp)
        # No second launch path and no user-controlled process input.
        for forbidden in ("QProcess", "build_launch_argv", "gio launch",
                          "g_app_info_launch", "QUrl(name)"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, cpp)

    def test_each_remaining_tile_has_one_exact_connection(self):
        cpp = self.cpp
        self.assertIn("static const QStringList remainingDockNames", cpp)
        self.assertIn("QObject::connect(tile, SIGNAL(activated(QString)),\n"
                      "                                 bridge, SLOT(activate(QString)))", cpp)
        self.assertIn("CANOPY_REMAINING_DOCK_NATIVE_LAUNCH_CONNECTED", cpp)
        block = cpp.split("static const QStringList remainingDockNames = {", 1)[1]
        block = block.split("};", 1)[0]
        for name in NAMES:
            with self.subTest(name=name):
                self.assertEqual(block.count(f'QStringLiteral("{name}")'), 1)
        gated = cpp.split("static const QStringList gatedDockNames = {", 1)[1]
        gated = gated.split("};", 1)[0]
        for name in NAMES:
            with self.subTest(name=name):
                self.assertNotIn(f'QStringLiteral("{name}")', gated)

    def test_refusal_is_visible_and_never_claims_success(self):
        cpp = self.cpp
        self.assertIn('"openLauncher"', cpp)
        self.assertIn("setProperty(\"selectionMessage\"", cpp)
        self.assertIn("could not be launched", cpp)
        self.assertIn("CANOPY_REMAINING_DOCK_STATUS_UNAVAILABLE", cpp)
        overlay = (SOURCE / "LauncherOverlay.qml").read_text(encoding="utf-8")
        self.assertIn('objectName: "canopyLauncherStatus"', overlay)
        self.assertIn("launcher.selectionMessage", overlay)

    def test_compiled_fixtures_expose_launch_and_status_cases(self):
        cpp = self.cpp
        self.assertIn("static bool runRemainingDockFixture", cpp)
        # Marker prefixes are composed from the exact frozen label at runtime;
        # assert both halves so no app-specific literal may be silently lost.
        for composed in ('QStringLiteral("_DOCK_STATUS_FIXTURE_PASS")',
                         'QStringLiteral("_DOCK_LAUNCH_FIXTURE_PASS")',
                         '"_DOCK_FIXTURE_FAIL: unknown action accepted"',
                         'QStringLiteral(";echo bad")'):
            with self.subTest(composed=composed):
                self.assertTrue(composed in cpp, f"missing {composed}")
        for name in NAMES:
            low = name.lower()
            with self.subTest(name=name):
                for token in (f'"--self-test-{low}-dock-status"',
                              f'"--self-test-{low}-dock-fixture"',
                              f'QStringLiteral("{name}")'):
                    self.assertTrue(token in cpp, f"missing {token}")

    def test_ci_exercises_isolated_gio_fixtures(self):
        wf = self.workflow
        for name in NAMES:
            low = name.lower()
            with self.subTest(name=name):
                self.assertIn(f"--self-test-{low}-dock-fixture", wf)
                self.assertIn(f"--self-test-{low}-dock-status", wf)
                self.assertIn(f"{low}-dock-launch-marker", wf)
                self.assertIn(DESKTOP_IDS[name], wf)
        self.assertIn("--approved-art-dir prototype/classic/assets/approved "
                      "--self-test-terminal-dock-fixture", wf)
        self.assertIn("tests.test_classic_remaining_dock_integration", wf)

    def test_frozen_visual_dock_and_assets_unchanged(self):
        main = (SOURCE / "Main.qml").read_text(encoding="utf-8")
        start = main.index("    Rectangle {\n        id: dock")
        self.assertEqual(fnv1a64(main[start:-1].encode("ascii")),
                         APPROVED_DOCK_FNV64)
        tile = (SOURCE / "DockTile.qml").read_text(encoding="utf-8")
        self.assertIn("signal activated(string applicationName)", tile)
        for name in NAMES:
            with self.subTest(name=name):
                self.assertNotIn(f'applicationName === "{name}"', main)


if __name__ == "__main__":
    unittest.main()
