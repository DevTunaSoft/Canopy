"""Offline unit tests for the reversible, unprivileged Classic preview package.

All binary and PNG bytes here are synthetic fixtures. They are NOT the compiled
Qt spike, NOT approved artwork and NOT proof of Linux Mint or visual acceptance.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import prepare_approved_art as art
from tools import register_classic_preview as reg
from tools.qa import classic_preview_package as pkg

ROOT = Path(__file__).resolve().parents[1]
ICON_SPECS = (
    ("Browser", "icons/Browser_Option_3.png"),
    ("Mail", "icons/Mail_Option_5.png"),
    ("Files", "icons/Files_Option_2.png"),
    ("Calendar", "icons/Calendar_Option_3.png"),
    ("Photos", "icons/Photos_Option_2.png"),
    ("Music", "icons/Music_Option_3.png"),
    ("Terminal", "icons/Terminal_Option_4.png"),
    ("Settings", "icons/Settings_Option_8.png"),
)
WALLPAPER_SPEC = ("Blue wave visual reference", "wallpaper/canopy-wave-preview.png")


class ClassicPreviewPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "xdg data with spaces"
        self.home.mkdir()
        self.binary = self.base / "canopy-classic-spike"
        self.binary.write_bytes(b"\x7fELF synthetic compiled binary fixture\n")
        # Linux requires the executable bit; Windows does not. The fixture
        # models a prebuilt executable while production validation remains
        # strict and test_nonexecutable_binary_rejected stays unchanged.
        self.binary.chmod(self.binary.stat().st_mode | 0o111)
        self.art_dir, self.manifest_path = self._build_fixtures()

    def _build_fixtures(self):
        art_dir = self.base / "approved art"
        icons = []
        for name, rel in ICON_SPECS:
            target = art_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            content = ("fixture:" + name).encode("utf-8")
            target.write_bytes(content)
            icons.append({"name": name, "path": rel,
                          "sha256": hashlib.sha256(content).hexdigest()})
        name, rel = WALLPAPER_SPEC
        wall_target = art_dir / rel
        wall_target.parent.mkdir(parents=True, exist_ok=True)
        wall_target.write_bytes(b"fixture:wave")
        wallpaper = {"name": name, "path": rel,
                     "sha256": hashlib.sha256(b"fixture:wave").hexdigest()}
        manifest = {
            "schema_version": 1,
            "source": "synthetic test fixture, not real approved art",
            "artwork_policy": "No substitution in real fixtures.",
            "icons": icons,
            "wallpaper": wallpaper,
        }
        manifest_path = self.base / "fixture-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return art_dir, manifest_path

    def _uid(self, value=1000):
        return patch.object(pkg, "_euid", return_value=value)

    def plan(self, **kwargs):
        with self._uid():
            return pkg.make_plan(self.home, self.binary, self.art_dir,
                                 manifest_path=self.manifest_path, **kwargs)

    def install(self, **kwargs):
        with self._uid():
            return pkg.install(self.home, self.binary, self.art_dir,
                               manifest_path=self.manifest_path, **kwargs)

    def uninstall(self):
        with self._uid():
            return pkg.uninstall(self.home)

    def status(self):
        with self._uid():
            return pkg.status(self.home)

    def fresh_home(self, name):
        home = self.base / name
        home.mkdir()
        return home

    def test_status_is_not_installed_initially(self):
        self.assertEqual(self.status(), "NOT_INSTALLED")

    def test_plan_is_a_dry_run_that_writes_nothing(self):
        plan = self.plan()
        self.assertFalse(plan["writes_files"])
        self.assertFalse(plan["requires_sudo"])
        self.assertEqual(pkg.status(self.home), "NOT_INSTALLED")
        self.assertFalse((self.home / "canopy").exists())
        self.assertFalse((self.home / "applications").exists())
        self.assertEqual(plan["package_root"],
                         str(self.home / "canopy" / "classic-preview-package"))
        self.assertEqual(len(plan["assets"]), 9)

    def test_plan_scope_denies_session_compositor_and_login_replacement(self):
        plan = self.plan()
        for forbidden in ("session", "compositor", "display manager",
                          "login manager"):
            self.assertIn(forbidden, plan["not_a"])
        self.assertIn("not a session", plan["scope"])

    def test_exec_paths_are_safely_quoted_and_minimal(self):
        plan = self.plan()
        binary = str(self.home / "canopy" / "classic-preview-package" / "bin"
                     / "canopy-classic-spike")
        art = str(self.home / "canopy" / "classic-preview-package" / "art")
        wallpaper = str(Path(art) / "wallpaper" / "canopy-wave-preview.png")
        command = plan["desktop_exec"]
        self.assertIn('"' + binary + '"', command)
        self.assertIn('"--approved-art-dir" "' + art + '"', command)
        self.assertIn('"--landscape-wallpaper" "' + wallpaper + '"', command)
        self.assertNotIn("sh -c", command)
        self.assertNotIn("--enable-system-apps", command)

    def test_special_exec_characters_rejected_before_any_write(self):
        for char in ('"', "\\", "$", chr(96), "%", "\n", "\r", "\x00"):
            if char == os.sep:
                continue
            with self.subTest(character=repr(char)):
                with self.assertRaises(pkg.PackageError):
                    pkg._quote("/tmp/name" + char + "unsafe")
        home = self.fresh_home("bad$home")
        with self._uid():
            with self.assertRaises(pkg.PackageError):
                pkg.make_plan(home, self.binary, self.art_dir,
                              manifest_path=self.manifest_path)
        self.assertFalse((home / "canopy").exists())

    def test_install_uninstall_round_trip_owns_only_expected_paths(self):
        manifest = self.install()
        self.assertTrue(manifest.is_file())
        self.assertEqual(self.status(), "INSTALLED")
        self.assertEqual(reg.status(self.home), "INSTALLED")
        p = pkg.package_paths(self.home)
        self.assertTrue(p["bin"].is_file())
        self.assertTrue(p["art"].is_dir())
        self.assertTrue(p["desktop"].is_file())
        text = p["desktop"].read_text(encoding="utf-8")
        self.assertIn("Name=Canopy Classic Preview", text)
        self.assertIn("not a replacement Cinnamon session", text)
        self.assertNotIn("sh -c", text)
        self.assertEqual(self.uninstall(), "UNINSTALLED")
        self.assertEqual(self.status(), "NOT_INSTALLED")
        self.assertEqual(reg.status(self.home), "NOT_INSTALLED")
        self.assertFalse(p["root"].exists())
        self.assertFalse(p["desktop"].exists())
        self.assertTrue(p["apps"].is_dir())
        self.assertTrue((self.home / "canopy").is_dir())

    def test_registration_is_delegated_to_existing_reversible_tool(self):
        self.install()
        p = pkg.package_paths(self.home)
        self.assertEqual(p["desktop"],
                         self.home / "applications" / reg.DESKTOP)
        marker = self.home / "canopy" / "classic-preview" / "ownership.json"
        self.assertTrue(marker.is_file())
        self.assertTrue(self.manifest_path.is_file())

    def test_plan_and_install_agree_on_the_registered_command(self):
        plan = self.plan()
        self.install()
        record = json.loads(
            (self.home / "canopy" / "classic-preview-package"
             / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["desktop_exec"], record["desktop_exec"])
        desktop = pkg.package_paths(self.home)["desktop"].read_text(encoding="utf-8")
        self.assertIn("Exec=" + record["desktop_exec"] + "\n", desktop)

    def test_binary_and_art_are_copied_not_moved(self):
        self.install()
        self.assertTrue(self.binary.is_file())
        for _, rel in ICON_SPECS:
            self.assertTrue((self.art_dir / rel).is_file())
        self.assertTrue((self.art_dir / WALLPAPER_SPEC[1]).is_file())

    def test_ownership_manifest_records_every_asset_hash(self):
        self.install()
        record = json.loads(
            (self.home / "canopy" / "classic-preview-package"
             / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], 1)
        self.assertEqual(record["kind"], "canopy-classic-preview-package")
        self.assertEqual(len(record["art"]), 9)
        self.assertEqual(record["wallpaper"], WALLPAPER_SPEC[1])
        self.assertEqual(record["binary"]["sha256"],
                         hashlib.sha256(self.binary.read_bytes()).hexdigest())
        self.assertIn("not a session", record["scope"])

    def test_install_twice_is_refused_without_overwrite(self):
        self.install()
        p = pkg.package_paths(self.home)
        before = p["desktop"].read_bytes()
        with self.assertRaises(pkg.PackageError):
            self.install()
        self.assertEqual(p["desktop"].read_bytes(), before)

    def test_preexisting_desktop_entry_is_not_overwritten(self):
        p = pkg.package_paths(self.home)
        p["apps"].mkdir(parents=True)
        p["desktop"].write_text("user's own entry", encoding="utf-8")
        with self.assertRaisesRegex(pkg.PackageError, "registration"):
            self.install()
        self.assertEqual(p["desktop"].read_text(encoding="utf-8"),
                         "user's own entry")

    def test_root_install_and_uninstall_are_both_refused(self):
        with self._uid(0):
            with self.assertRaisesRegex(pkg.PackageError, "root"):
                pkg.install(self.home, self.binary, self.art_dir,
                            manifest_path=self.manifest_path)
            with self.assertRaisesRegex(pkg.PackageError, "root"):
                pkg.uninstall(self.home)

    def test_relative_and_missing_and_symlinked_binary_rejected(self):
        alias = self.base / "linked-binary"
        alias.symlink_to(self.binary)
        for candidate in ("relative-binary", self.base / "missing",
                          alias):
            with self.subTest(candidate=str(candidate)):
                with self._uid():
                    with self.assertRaises(pkg.PackageError):
                        pkg.install(self.home, candidate, self.art_dir,
                                    manifest_path=self.manifest_path)
        self.assertEqual(self.status(), "NOT_INSTALLED")
        self.assertTrue(self.binary.is_file())

    def test_nonexecutable_binary_rejected(self):
        with patch.object(pkg, "_is_executable", return_value=False):
            with self._uid():
                with self.assertRaisesRegex(pkg.PackageError, "executable"):
                    pkg.install(self.home, self.binary, self.art_dir,
                                manifest_path=self.manifest_path)
        self.assertEqual(self.status(), "NOT_INSTALLED")

    def test_unsafe_art_directories_rejected(self):
        link = self.base / "art-link"
        link.symlink_to(self.art_dir, target_is_directory=True)
        for candidate in ("relative-art", link, self.base / "no-art"):
            with self.subTest(candidate=str(candidate)):
                with self._uid():
                    with self.assertRaises(pkg.PackageError):
                        pkg.install(self.home, self.binary, candidate,
                                    manifest_path=self.manifest_path)
        self.assertEqual(self.status(), "NOT_INSTALLED")

    def test_missing_and_tampered_art_is_rejected_before_writes(self):
        (self.art_dir / "icons" / "Files_Option_2.png").unlink()
        with self._uid():
            with self.assertRaises(pkg.PackageError):
                pkg.install(self.home, self.binary, self.art_dir,
                            manifest_path=self.manifest_path)
        self.assertFalse((self.home / "canopy").exists())
        (self.art_dir / "icons" / "Files_Option_2.png").write_bytes(b"tampered")
        with self._uid():
            with self.assertRaises(pkg.PackageError):
                pkg.install(self.home, self.binary, self.art_dir,
                            manifest_path=self.manifest_path)
        self.assertEqual(self.status(), "NOT_INSTALLED")

    def test_traversal_in_approved_manifest_is_rejected(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["icons"][0]["path"] = "../../escape.png"
        bad = self.base / "traversal-manifest.json"
        bad.write_text(json.dumps(manifest), encoding="utf-8")
        with self._uid():
            with self.assertRaises(pkg.PackageError):
                pkg.install(self.home, self.binary, self.art_dir,
                            manifest_path=bad)
        self.assertEqual(self.status(), "NOT_INSTALLED")

    def test_wrong_artwork_manifest_names_are_rejected(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["icons"][0]["name"] = "Substitute"
        bad = self.base / "wrong-manifest.json"
        bad.write_text(json.dumps(manifest), encoding="utf-8")
        with self._uid():
            with self.assertRaises(pkg.PackageError):
                pkg.install(self.home, self.binary, self.art_dir,
                            manifest_path=bad)
        self.assertEqual(self.status(), "NOT_INSTALLED")

    def test_symlinked_package_root_is_unsafe_and_refused(self):
        external = self.base / "outside"
        external.mkdir()
        (self.home / "canopy").symlink_to(external, target_is_directory=True)
        self.assertEqual(self.status(), "UNSAFE")
        with self._uid():
            with self.assertRaises(pkg.PackageError):
                self.install()
        self.assertEqual(list(external.iterdir()), [])

    def test_modified_binary_prevents_uninstall_without_deleting(self):
        self.install()
        p = pkg.package_paths(self.home)
        p["bin"].write_bytes(b"replaced by user")
        self.assertEqual(self.status(), "MODIFIED_OR_UNMANAGED")
        with self.assertRaisesRegex(pkg.PackageError, "not exact-byte owned"):
            self.uninstall()
        self.assertTrue(p["bin"].is_file())
        self.assertTrue(p["desktop"].is_file())

    def test_modified_art_prevents_uninstall_without_deleting(self):
        self.install()
        p = pkg.package_paths(self.home)
        (p["art"] / "icons" / "Photos_Option_2.png").write_bytes(b"changed")
        self.assertEqual(self.status(), "MODIFIED_OR_UNMANAGED")
        with self.assertRaises(pkg.PackageError):
            self.uninstall()
        self.assertTrue(p["root"].is_dir())

    def test_modified_desktop_entry_prevents_uninstall(self):
        self.install()
        p = pkg.package_paths(self.home)
        p["desktop"].write_text(
            p["desktop"].read_text(encoding="utf-8") + "# user note\n",
            encoding="utf-8")
        self.assertEqual(reg.status(self.home), "MODIFIED_OR_UNMANAGED")
        self.assertEqual(self.status(), "MODIFIED_OR_UNMANAGED")
        with self.assertRaises(pkg.PackageError):
            self.uninstall()
        self.assertTrue(p["desktop"].is_file())

    def test_extra_user_file_in_package_prevents_uninstall(self):
        self.install()
        p = pkg.package_paths(self.home)
        extra = p["root"] / "my-notes.txt"
        extra.write_text("keep this", encoding="utf-8")
        with self.assertRaises(pkg.PackageError):
            self.uninstall()
        self.assertEqual(extra.read_text(encoding="utf-8"), "keep this")

    def test_uninstall_retains_unrelated_user_files(self):
        apps = self.home / "applications"
        apps.mkdir()
        other = apps / "another-program.desktop"
        other.write_text("other entry", encoding="utf-8")
        canopy_other = self.home / "canopy" / "note.txt"
        canopy_other.parent.mkdir()
        canopy_other.write_text("keep", encoding="utf-8")
        self.install()
        self.assertEqual(self.uninstall(), "UNINSTALLED")
        self.assertEqual(other.read_text(encoding="utf-8"), "other entry")
        self.assertEqual(canopy_other.read_text(encoding="utf-8"), "keep")

    def test_partial_failure_rolls_back_staged_and_registered_files(self):
        original = Path.open
        def refuse_manifest(path, *args, **kwargs):
            if Path(path).name == "package.json" and "x" in args[0]:
                raise OSError("simulated full disk")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", autospec=True, side_effect=refuse_manifest):
            with self._uid():
                with self.assertRaises(OSError):
                    self.install()
        self.assertEqual(self.status(), "NOT_INSTALLED")
        self.assertEqual(reg.status(self.home), "NOT_INSTALLED")
        self.assertFalse((self.home / "canopy" / "classic-preview-package").exists())
        self.assertFalse((self.home / "applications" / reg.DESKTOP).exists())

    def test_no_sudo_daemon_or_compositor_behavior_in_source(self):
        source = (ROOT / "tools" / "qa" / "classic_preview_package.py").read_text(
            encoding="utf-8")
        for forbidden in ("Popen", "systemd", "systemctl",
                          "start_new_session", "os.system", "subprocess"):
            self.assertNotIn(forbidden, source)
        self.assertIn("EXPERIMENTAL APPLICATION PREVIEW", source)
        self.assertIn("not a session, compositor", source)

    def test_cli_plan_status_install_uninstall(self):
        env = dict(os.environ)
        env["XDG_DATA_HOME"] = str(self.home)
        cli = [sys.executable, str(ROOT / "tools" / "qa"
                                   / "classic_preview_package.py")]

        def run(*args):
            return subprocess.run(cli + list(args), cwd=ROOT, env=env,
                                  capture_output=True, text=True, check=False)

        status = run("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("CANOPY_PACKAGE_NOT_INSTALLED", status.stdout)

        plan = run("plan", "--binary", str(self.binary),
                   "--approved-art-dir", str(self.art_dir),
                   "--manifest", str(self.manifest_path))
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertIn('"writes_files": false', plan.stdout)
        self.assertIn("classic-preview-package", plan.stdout)

        installed = run("install", "--binary", str(self.binary),
                        "--approved-art-dir", str(self.art_dir),
                        "--manifest", str(self.manifest_path))
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertIn("CANOPY_PACKAGE_INSTALLED", installed.stdout)
        self.assertIn("CANOPY_PACKAGE_INSTALLED", run("status").stdout)

        removed = run("uninstall")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertIn("CANOPY_PACKAGE_UNINSTALLED", removed.stdout)
        self.assertIn("CANOPY_PACKAGE_NOT_INSTALLED", run("status").stdout)

    def test_cli_rejects_relative_xdg_data_home(self):
        env = dict(os.environ)
        env["XDG_DATA_HOME"] = "relative"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "qa"
                                 / "classic_preview_package.py"), "status"],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("absolute", proc.stderr)


if __name__ == "__main__":
    unittest.main()
