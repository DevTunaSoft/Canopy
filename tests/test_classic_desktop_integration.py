"""Source contracts for the opt-in native app launcher on the Classic Qt port.

These are not Qt runtime tests. They guard that the ported GIO launcher stays
host-owned, opt-in and shell-free, and that the frozen visual dock is untouched.
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


class ClassicDesktopIntegrationTests(unittest.TestCase):
    def test_host_launcher_files_exist(self):
        for name in ("SystemAppLauncher.h", "SystemAppLauncher.cpp"):
            with self.subTest(name=name):
                self.assertTrue((SOURCE / name).is_file())

    def test_launcher_is_gio_based_opt_in_and_shell_free(self):
        header = (SOURCE / "SystemAppLauncher.h").read_text(encoding="utf-8")
        cpp = (SOURCE / "SystemAppLauncher.cpp").read_text(encoding="utf-8")
        self.assertIn("g_desktop_app_info_new", cpp)
        self.assertIn("g_app_info_should_show", cpp)
        self.assertIn("g_app_info_launch", cpp)
        self.assertIn("m_enabled", header)
        self.assertNotIn("QProcess", header + cpp)
        self.assertNotIn("QProcess", (SOURCE / "main.cpp").read_text(encoding="utf-8"))
        self.assertIn("SYSTEM_APP_LAUNCH_TEST_PASS", (SOURCE / "main.cpp").read_text(encoding="utf-8"))

    def test_fixed_allowlist_only(self):
        cpp = (SOURCE / "SystemAppLauncher.cpp").read_text(encoding="utf-8")
        for name in ("Browser", "Mail", "Files", "Calendar",
                     "Photos", "Music", "Terminal", "Settings"):
            self.assertIn(f'QStringLiteral("{name}")', cpp)
        self.assertIn("candidates.value(dockName)", cpp)

    def test_cmake_builds_and_links_gio(self):
        text = (SOURCE / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("find_package(PkgConfig REQUIRED)", text)
        self.assertIn("gio-unix-2.0", text)
        self.assertIn("SystemAppLauncher.cpp SystemAppLauncher.h", text)
        self.assertIn("PkgConfig::GIO_UNIX", text)

    def test_main_exposes_flag_selftests_and_bridge(self):
        cpp = (SOURCE / "main.cpp").read_text(encoding="utf-8")
        for marker in ("--enable-system-apps",
                       "--self-test-system-apps",
                       "--self-test-system-apps-fixture",
                       "--self-test-launcher-launch-fixture",
                       "SYSTEM_APP_LAUNCH_FIXTURE_PASS",
                       "SYSTEM_APP_LAUNCH_TEST_PASS",
                       "canopySystemLauncher",
                       "canopySystemLaunchEnabled",
                       "SIGNAL(activated(QString))",
                       "SLOT(launch(QString))",
                       "LAUNCHER_LAUNCH_FIXTURE_PASS"):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)

    def test_launcher_overlay_uses_host_launcher_first(self):
        overlay = (SOURCE / "LauncherOverlay.qml").read_text(encoding="utf-8")
        self.assertIn("canopySystemLaunchEnabled && canopySystemLauncher.launch(name)", overlay)
        self.assertIn("applicationSelected(name)", overlay)
        self.assertIn('selectionMessage = name + " is not connected in this preview"', overlay)

    def test_frozen_visual_dock_unchanged(self):
        # read_text() uses universal newlines, so this holds on both LF CI and
        # CRLF Windows checkouts. Raw-byte blob hashes do not (core.autocrlf).
        main = (SOURCE / "Main.qml").read_text(encoding="utf-8")
        start = main.index("    Rectangle {\n        id: dock")
        self.assertEqual(fnv1a64(main[start:-1].encode("ascii")),
                         APPROVED_DOCK_FNV64)


if __name__ == "__main__":
    unittest.main()
