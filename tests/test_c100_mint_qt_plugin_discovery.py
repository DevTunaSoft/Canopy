"""Offline unit tests for read-only Qt plugin evidence inspection.

Synthetic plugin trees exercise Windows and Linux/Mint naming without a
real Mint guest or compiled Qt. A green test here is NOT Mint acceptance.
"""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.mint import qt_plugin_discovery as discovery


class QtPluginDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.images = ["qsvg.so", "qpng.so", "qjpeg.dll"]
        self.platforms = ["qxcb.so", "qoffscreen.so"]

    def probe(self, **kwargs):
        return discovery.assess(
            kwargs.get("images", self.images),
            kwargs.get("platforms", self.platforms),
            kwargs.get("version", "6.4.2"),
            kwargs.get("session", "x11"),
        )

    def assert_never_acceptance(self, report):
        self.assertTrue(report["probe_only"])
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
        self.assertEqual(report["runtime_functional_test"], "NOT_RUN")
        self.assertEqual(report["visual_acceptance"], "NOT_RUN")

    def test_compatible_x11_evidence_is_ok(self):
        report = self.probe()
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["qt_version_compatible"])
        self.assertTrue(report["svg_plugin_present"])
        self.assertTrue(report["platform_plugin_present"])
        self.assertEqual(report["qt_version"], "6.4.2")
        self.assertEqual(report["expected_platform_plugins"], ["qxcb"])
        self.assert_never_acceptance(report)

    def test_missing_svg_plugin_is_blocked(self):
        report = self.probe(images=["qpng.so", "qjpeg.so"])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["svg_plugin_present"])
        self.assertIn("qsvg", report["missing_image_plugins"])
        self.assertTrue(any("qsvg" in text for text in report["blockers"]))
        self.assert_never_acceptance(report)

    def test_incompatible_and_invalid_versions_are_blocked(self):
        cases = {
            "5.15.2": "incompatible Qt major version",
            "6.3.2": "below required",
            "4.8.7": "incompatible Qt major version",
            "7.0.0": "incompatible Qt major version",
            "6": "below required",
            None: "unavailable or unparseable",
            "banana": "unavailable or unparseable",
            "6.4.2.1.5": "unavailable or unparseable",
            "6.4.x": "unavailable or unparseable",
        }
        for version, reason in cases.items():
            with self.subTest(version=version):
                report = self.probe(version=version)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["qt_version_compatible"])
                self.assertTrue(any(reason in text for text in report["blockers"]))

    def test_supported_versions_pass(self):
        for version in ("6.4", "6.4.0", "6.9.3", " 6.5.1 "):
            with self.subTest(version=version):
                report = self.probe(version=version)
                self.assertEqual(report["status"], "OK")
                self.assertTrue(report["qt_version_compatible"])

    def test_wayland_and_headless_platform_requirements(self):
        wayland = self.probe(session="wayland", platforms=["qwayland.so"])
        self.assertEqual(wayland["status"], "OK")
        self.assertTrue(wayland["platform_plugin_present"])

        wrong = self.probe(session="wayland", platforms=["qxcb.so"])
        self.assertEqual(wrong["status"], "BLOCKED")
        self.assertIn("qwayland", wrong["missing_platform_plugins"])

        headless = self.probe(session="headless", platforms=["qminimal.so"])
        self.assertEqual(headless["status"], "OK")
        self.assertEqual(headless["expected_platform_plugins"],
                         ["qoffscreen", "qminimal"])

    def test_unknown_session_does_not_guess_platform(self):
        report = self.probe(session="secret-session-value")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["session"], "other-or-unknown")
        self.assertEqual(report["expected_platform_plugins"], [])
        self.assertEqual(report["missing_platform_plugins"], [])
        self.assertFalse(report["platform_plugin_present"])
        self.assertNotIn("secret-session-value", json.dumps(report))

    def test_windows_and_linux_plugin_names_normalize(self):
        cases = {
            "qsvg.so": "qsvg",
            "qsvg.so.6": "qsvg",
            "qsvg.dll": "qsvg",
            "qwindows.dll": "qwindows",
            "libqsvg.so": "qsvg",
            "QPNG.DYLIB": "qpng",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(discovery.normalize_plugin_name(filename), expected)
        for filename in ("README.txt", "q bad.so", "q", "", "q\\evil.so",
                         "q" * 200, None, 7):
            with self.subTest(filename=filename):
                self.assertIsNone(discovery.normalize_plugin_name(filename))

    def test_hostile_names_cannot_manufacture_a_plugin_present_claim(self):
        # A suffix match anywhere in the name used to be split away, so a
        # bounded hostile file name became "qsvg" and yielded status OK even
        # though no real qsvg plugin was observed.
        hostile = ("qsvg.so\0.evil", "qsvg.so\n.evil", "qsvg.so\x1c.evil",
                   "qsvg.so\t.lib", "qsvg.so;.evil", "qsvg.so.evil")
        for filename in hostile:
            with self.subTest(filename=filename):
                self.assertIsNone(discovery.normalize_plugin_name(filename))
                report = self.probe(images=[filename])
                self.assertFalse(report["svg_plugin_present"])
                self.assertEqual(report["image_plugins"], [])
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(report["missing_image_plugins"], ["qsvg"])

        # A real versioned shared object must still normalize to the plugin key.
        self.assertEqual(discovery.normalize_plugin_name("qsvg.so.6"), "qsvg")
        self.assertEqual(discovery.normalize_plugin_name("qsvg.so.6.2"), "qsvg")

    def test_assess_normalizes_raw_plugin_filenames(self):
        report = self.probe(
            images=["qsvg.dll", "qpng.dll"],
            platforms=["qwindows.dll"],
            session="headless",
        )
        self.assertEqual(report["image_plugins"], ["qpng", "qsvg"])
        self.assertEqual(report["platform_plugins"], ["qwindows"])
        self.assertTrue(report["svg_plugin_present"])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["missing_platform_plugins"],
                         ["qoffscreen", "qminimal"])

    def test_collect_reads_synthetic_plugin_tree_without_side_effects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "qt6" / "plugins"
            (root / "imageformats").mkdir(parents=True)
            (root / "platforms").mkdir()
            (root / "imageformats" / "qsvg.so").write_bytes(b"fixture")
            (root / "imageformats" / "qpng.so").write_bytes(b"fixture")
            (root / "imageformats" / "README.txt").write_text("ignore")
            (root / "platforms" / "qxcb.so").write_bytes(b"fixture")
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            environ = dict(os.environ)

            report = discovery.collect(root, session="x11", qt_version="6.5.1")

            self.assertEqual(report["status"], "OK")
            self.assertEqual(report["image_plugins"], ["qpng", "qsvg"])
            self.assertEqual(report["platform_plugins"], ["qxcb"])
            self.assertEqual(sorted(str(path.relative_to(root))
                                    for path in root.rglob("*")), before)
            self.assertEqual(dict(os.environ), environ)
            self.assertNotIn(str(root), json.dumps(report))

    def test_collect_ignores_symlinks_and_nested_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plugins"
            (root / "imageformats").mkdir(parents=True)
            (root / "platforms").mkdir()
            (root / "imageformats" / "qsvg.so").write_bytes(b"fixture")
            nested = root / "imageformats" / "nested"
            nested.mkdir()
            (nested / "qjpeg.so").write_bytes(b"fixture")
            outside = Path(temp) / "outside.so"
            outside.write_bytes(b"fixture")
            (root / "imageformats" / "qlinked.so").symlink_to(outside)

            report = discovery.collect(root, session="x11", qt_version="6.4.2")

            self.assertEqual(report["image_plugins"], ["qsvg"])

    def test_collect_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plugins"
            (root / "imageformats").mkdir(parents=True)
            (root / "platforms").mkdir()
            for index in range(8):
                (root / "imageformats" / f"qimage{index}.so").write_bytes(b"x")
            with patch.object(discovery, "MAX_ENTRIES", 3):
                report = discovery.collect(root, session="headless",
                                           qt_version="6.4.2")
            self.assertEqual(len(report["image_plugins"]), 3)

    def test_collect_missing_directory_is_blocked_not_crash(self):
        with tempfile.TemporaryDirectory() as temp:
            report = discovery.collect(Path(temp) / "absent", session="x11",
                                       qt_version="6.4.2")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["image_plugins"], [])
        self.assertEqual(report["platform_plugins"], [])
        self.assertEqual(report["missing_image_plugins"], ["qsvg"])
        self.assertEqual(report["missing_platform_plugins"], ["qxcb"])

    def test_cli_reports_evidence_without_accepting_mint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plugins"
            (root / "imageformats").mkdir(parents=True)
            (root / "platforms").mkdir()
            (root / "imageformats" / "qsvg.so").write_bytes(b"fixture")
            (root / "platforms" / "qxcb.so").write_bytes(b"fixture")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = discovery.main([
                    "--plugins-root", str(root), "--session", "x11",
                    "--qt-version", "6.4.2", "--json",
                ])
            self.assertEqual(code, 0)
            report = json.loads(buffer.getvalue())
            self.assertEqual(report["status"], "OK")
            self.assert_never_acceptance(report)

            with redirect_stdout(io.StringIO()):
                missing = discovery.main([
                    "--plugins-root", str(root), "--session", "x11",
                    "--qt-version", "5.15.2", "--json",
                ])
            self.assertEqual(missing, 1)


if __name__ == "__main__":
    unittest.main()
