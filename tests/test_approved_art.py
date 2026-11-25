"""Artwork contract: the selected user icon PNGs must be used byte-for-byte."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_approved_art import (
    ArtworkError, MANIFEST, check_exact, prepare, read_manifest
)

REPO = Path(__file__).resolve().parents[1]


class ApprovedArtworkTests(unittest.TestCase):
    def test_locked_eight_name_and_option_sequence(self):
        data = read_manifest()
        self.assertEqual(
            [(i["name"], Path(i["path"]).name) for i in data["icons"]],
            [
                ("Browser", "Browser_Option_3.png"),
                ("Mail", "Mail_Option_5.png"),
                ("Files", "Files_Option_2.png"),
                ("Calendar", "Calendar_Option_3.png"),
                ("Photos", "Photos_Option_2.png"),
                ("Music", "Music_Option_3.png"),
                ("Terminal", "Terminal_Option_4.png"),
                ("Settings", "Settings_Option_8.png"),
            ],
        )

    def test_manifest_is_embedded_in_qt_and_not_dummy_assets(self):
        cmake = (REPO / "prototype/classic/CMakeLists.txt").read_text()
        self.assertIn("assets/approved/manifest.json", cmake)
        source = (REPO / "prototype/classic/main.cpp").read_text()
        self.assertIn("verifyExactArtwork(", source)
        self.assertIn("QCryptographicHash::Sha256", source)
        self.assertIn("CANOPY_APPROVED_ART_VERIFIED", source)
        self.assertIn("--approved-art-dir", source)
        self.assertIn("--self-test-approved", source)
        self.assertIn("SHA-256 mismatch, refusing substitute", source)
        self.assertIn("SELF_TEST_PASS: all eight exact approved dock PNGs loaded", source)
        qml = (REPO / "prototype/classic/DockTile.qml").read_text()
        wallpaper = (REPO / "prototype/classic/Wallpaper.qml").read_text()
        self.assertIn("canopyApprovedMode", qml)
        self.assertIn("image://canopy-dock/", qml)
        self.assertIn("canopyApprovedWallpaperUrl", wallpaper)
        self.assertNotIn("ShaderEffect", wallpaper)

    def test_tampered_png_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.png"
            data = b"not-the-approved-icon"
            path.write_bytes(data)
            with self.assertRaisesRegex(ArtworkError, "no substitutions"):
                check_exact(path, hashlib.sha256(b"other-bytes").hexdigest())

    def test_missing_source_refuses_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            with self.assertRaisesRegex(ArtworkError, "missing"):
                prepare(root / "icons", root / "background.png", output)
            self.assertFalse(output.exists())

    def test_manifest_refuses_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            modified = json.loads(MANIFEST.read_text())
            modified["icons"][0]["path"] = "../sneaky.png"
            fixture = Path(tmp) / "manifest.json"
            fixture.write_text(json.dumps(modified))
            with self.assertRaisesRegex(ArtworkError, "Invalid approved asset path"):
                read_manifest(fixture)

    def test_manifest_rejects_changed_icon_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            modified = json.loads(MANIFEST.read_text())
            modified["icons"][0]["name"] = "OtherBrowser"
            fixture = Path(tmp) / "manifest.json"
            fixture.write_text(json.dumps(modified))
            with self.assertRaisesRegex(ArtworkError, "approved selection"):
                read_manifest(fixture)

    def test_complete_install_is_atomic_idempotent_and_byte_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icons = root / "sources"
            icons.mkdir()
            wallpaper = root / "wave.png"
            data = read_manifest()
            for i, entry in enumerate(data["icons"]):
                payload = b"fixture-icon-for-installer-not-UI-" + str(i).encode()
                (icons / Path(entry["path"]).name).write_bytes(payload)
                entry["sha256"] = hashlib.sha256(payload).hexdigest()
            wallpaper_bytes = b"fixture-wave-for-installer-only"
            wallpaper.write_bytes(wallpaper_bytes)
            data["wallpaper"]["sha256"] = hashlib.sha256(wallpaper_bytes).hexdigest()
            fixture_manifest = root / "fixture.json"
            fixture_manifest.write_text(json.dumps(data), encoding="utf-8")
            output = root / "approved-art"
            prepare(icons, wallpaper, output, fixture_manifest)
            self.assertEqual(len(list((output / "icons").glob("*.png"))), 8)
            self.assertEqual(
                (output / "wallpaper/canopy-wave-preview.png").read_bytes(),
                wallpaper_bytes,
            )
            for entry in data["icons"]:
                self.assertEqual(
                    (output / entry["path"]).read_bytes(),
                    (icons / Path(entry["path"]).name).read_bytes(),
                )
            prepare(icons, wallpaper, output, fixture_manifest)  # Safe no-op.
            corrupted = output / data["icons"][0]["path"]
            corrupted.write_bytes(b"changed")
            with self.assertRaisesRegex(ArtworkError, "no substitutions"):
                prepare(icons, wallpaper, output, fixture_manifest)

    def test_reject_symlink_as_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "original.png"
            target.write_bytes(b"correct-bytes")
            link = root / "shortcut.png"
            link.symlink_to(target)
            with self.assertRaisesRegex(ArtworkError, "symlink"):
                check_exact(link, hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
