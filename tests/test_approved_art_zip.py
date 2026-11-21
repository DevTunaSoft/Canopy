"""Regression checks for immutable, fail-closed Canopy Classic ZIP import.

Test PNG bytes are synthetic fixtures only, not approved artwork or GUI proof.
"""
import hashlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from tools.install_approved_art_zip import ArtworkError, install_archive
from tools.prepare_approved_art import read_manifest

ROOT = Path(__file__).resolve().parents[1]


def fixture(root: Path, *, omit=None, tamper=None, unexpected=None,
            changed_manifest=False, link=None, duplicate=None):
    manifest = json.loads(json.dumps(read_manifest()))
    entries = [*manifest["icons"], manifest["wallpaper"]]
    pngs = {}
    for i, entry in enumerate(entries):
        content = b"fixture-not-an-image:" + str(i).encode("ascii")
        pngs["approved-art/" + entry["path"]] = content
        entry["sha256"] = hashlib.sha256(content).hexdigest()
    manifest_path = root / "fixture-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    archive_path = root / "art.zip"
    with ZipFile(archive_path, "w") as archive:
        archived_manifest = dict(manifest)
        if changed_manifest:
            archived_manifest["source"] = "untrusted provenance"
        archive.writestr("approved-art/manifest.json",
                         json.dumps(archived_manifest))
        for name, data in pngs.items():
            if name == omit:
                continue
            if name == link:
                info = ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "outside-file")
            else:
                archive.writestr(name, b"changed" if name == tamper else data)
        if unexpected:
            archive.writestr(unexpected, b"not allowed")
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(duplicate, b"again")
    return archive_path, manifest_path, pngs


class ApprovedZipInstallerTests(unittest.TestCase):
    def test_valid_archive_installs_all_nine_unchanged_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, pngs = fixture(root)
            output = root / "artwork"
            install_archive(archive, output, manifest)
            for name, content in pngs.items():
                self.assertEqual((output / name.removeprefix("approved-art/")).read_bytes(),
                                 content)
            self.assertEqual(len(list(output.rglob("*.png"))), 9)
            install_archive(archive, output, manifest)

    def test_missing_asset_fails_without_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = "approved-art/icons/Browser_Option_3.png"
            archive, manifest, _ = fixture(root, omit=missing)
            output = root / "artwork"
            with self.assertRaisesRegex(ArtworkError, "missing"):
                install_archive(archive, output, manifest)
            self.assertFalse(output.exists())

    def test_tampered_asset_fails_without_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, _ = fixture(
                root, tamper="approved-art/icons/Files_Option_2.png")
            output = root / "artwork"
            with self.assertRaisesRegex(ArtworkError, "SHA-256 mismatch"):
                install_archive(archive, output, manifest)
            self.assertFalse(output.exists())

    def test_extra_traversal_path_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, _ = fixture(root, unexpected="../escape.png")
            with self.assertRaisesRegex(ArtworkError, "unexpected ZIP path"):
                install_archive(archive, root / "artwork", manifest)
            self.assertFalse((root / "artwork").exists())

    def test_duplicate_member_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, _ = fixture(
                root, duplicate="approved-art/icons/Browser_Option_3.png")
            with self.assertRaisesRegex(ArtworkError, "Duplicate"):
                install_archive(archive, root / "artwork", manifest)

    def test_provenance_manifest_must_match_local_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, _ = fixture(root, changed_manifest=True)
            with self.assertRaisesRegex(ArtworkError, "provenance"):
                install_archive(archive, root / "artwork", manifest)

    def test_symlink_member_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, _ = fixture(
                root, link="approved-art/icons/Browser_Option_3.png")
            with self.assertRaisesRegex(ArtworkError, "symlink"):
                install_archive(archive, root / "artwork", manifest)

    def test_existing_modified_install_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, _ = fixture(root)
            output = root / "artwork"
            install_archive(archive, output, manifest)
            altered = output / "icons/Browser_Option_3.png"
            altered.write_bytes(b"modified")
            with self.assertRaisesRegex(ArtworkError, "no substitutions"):
                install_archive(archive, output, manifest)
            self.assertEqual(altered.read_bytes(), b"modified")

    def test_archive_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, manifest, _ = fixture(root)
            link = root / "art-shortcut.zip"
            link.symlink_to(archive)
            with self.assertRaisesRegex(ArtworkError, "symlink"):
                install_archive(link, root / "artwork", manifest)

    def test_direct_cli_invocation_has_working_imports(self):
        result = subprocess.run(
            [sys.executable, "tools/install_approved_art_zip.py", "--help"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--archive", result.stdout)
        self.assertIn("--destination", result.stdout)


if __name__ == "__main__":
    unittest.main()
