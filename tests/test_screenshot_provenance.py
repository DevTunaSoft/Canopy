"""Offline regression checks for screenshot evidence provenance metadata.

These tests fail closed on bad PNGs, path escapes, symlinks, duplicate
entries and hash/dimension mismatches.  They never render a GUI or install
assets; PNGs are synthetic fixtures created inside a temporary directory.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from tools.check_screenshot_provenance import (
    DISCLAIMER,
    ProvenanceValidationError,
    validate_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_screenshot_provenance.py"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _make_png(width, height, color_type=2, bit_depth=8):
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    row_bytes = (width * channels * bit_depth + 7) // 8
    raw = b"".join(b"\x00" + b"\x00" * row_bytes for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


class ScreenshotProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "shots").mkdir()
        self.bytes_1080 = _make_png(1920, 1080)
        self.bytes_720 = _make_png(1280, 720)
        (self.root / "shots" / "classic-1080p.png").write_bytes(self.bytes_1080)
        (self.root / "shots" / "classic-720p.png").write_bytes(self.bytes_720)
        self.manifest = {
            "manifest_version": 1,
            "source_commit": "a" * 40,
            "capture_command": "python tools/mint_classic_qt_smoke.py --capture",
            "entries": [
                {
                    "path": "shots/classic-1080p.png",
                    "width": 1920,
                    "height": 1080,
                    "sha256": hashlib.sha256(self.bytes_1080).hexdigest(),
                },
                {
                    "path": "shots/classic-720p.png",
                    "width": 1280,
                    "height": 720,
                    "sha256": hashlib.sha256(self.bytes_720).hexdigest(),
                },
            ],
        }
        self.manifest_path = self.root / "manifest.json"
        self.write_manifest()

    def write_manifest(self, raw=None):
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=2) if raw is None else raw,
            encoding="utf-8",
        )

    def reject(self, message):
        with self.assertRaisesRegex(ProvenanceValidationError, message):
            validate_provenance(self.manifest_path)

    def replace_entry_bytes(self, index, data, dimensions=None):
        entry = self.manifest["entries"][index]
        (self.root / entry["path"]).write_bytes(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        if dimensions is not None:
            entry["width"], entry["height"] = dimensions
        self.write_manifest()

    def test_valid_manifest_passes(self):
        result = validate_provenance(self.manifest_path)
        self.assertEqual(len(result["entries"]), 2)

    def test_disclaimer_explicitly_limits_claim(self):
        text = DISCLAIMER.lower()
        self.assertIn("compiled qt", text)
        self.assertIn("visual approval", text)

    def test_cli_pass_includes_disclaimer(self):
        done = subprocess.run(
            [sys.executable, str(CHECKER), str(self.manifest_path)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("SCREENSHOT_PROVENANCE_PASS", done.stdout)
        self.assertIn("visual approval", done.stdout)

    def test_cli_fails_closed_on_bad_entry(self):
        self.manifest["entries"][0]["sha256"] = "0" * 64
        self.write_manifest()
        done = subprocess.run(
            [sys.executable, str(CHECKER), str(self.manifest_path)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 1)
        self.assertIn("SCREENSHOT_PROVENANCE_FAIL", done.stderr)

    def test_corrupt_png_signature_rejected(self):
        corrupted = b"\x00" + self.bytes_1080[1:]
        self.replace_entry_bytes(0, corrupted)
        self.reject("corrupt PNG signature")

    def test_ihdr_not_first_chunk_rejected(self):
        ihdr = struct.pack(">IIBBBBB", 1920, 1080, 8, 2, 0, 0, 0)
        reordered = (
            PNG_SIGNATURE
            + _chunk(b"IDAT", zlib.compress(b"\x00" * 64))
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IEND", b"")
        )
        self.replace_entry_bytes(0, reordered)
        self.reject("IHDR must be the first PNG chunk")

    def test_truncated_png_rejected(self):
        self.replace_entry_bytes(0, self.bytes_1080[:-4])
        self.reject("truncated|incomplete")

    def test_bad_png_crc_rejected(self):
        data = bytearray(self.bytes_1080)
        data[-20] ^= 0xFF
        self.replace_entry_bytes(0, bytes(data))
        self.reject("CRC mismatch")

    def test_missing_iend_rejected(self):
        head = self.bytes_1080[:self.bytes_1080.rfind(b"IEND") - 4]
        self.replace_entry_bytes(0, head)
        self.reject("truncated|incomplete")

    def test_unsupported_dimensions_rejected(self):
        entry = self.manifest["entries"][0]
        entry["width"], entry["height"] = 999, 999
        self.write_manifest()
        self.reject("unsupported dimensions")

    def test_dimension_mismatch_rejected(self):
        self.replace_entry_bytes(0, self.bytes_1080, dimensions=(1280, 720))
        self.reject("do not match declared")

    def test_hash_mismatch_rejected(self):
        self.manifest["entries"][0]["sha256"] = "0" * 64
        self.write_manifest()
        self.reject("sha256 mismatch")

    def test_path_traversal_rejected(self):
        self.manifest["entries"][0]["path"] = "shots/../secret.png"
        self.write_manifest()
        self.reject("traversal component")

    def test_path_escape_rejected(self):
        self.manifest["entries"][0]["path"] = "../outside.png"
        self.write_manifest()
        self.reject("traversal component")

    def test_absolute_path_rejected(self):
        self.manifest["entries"][0]["path"] = "/tmp/evil.png"
        self.write_manifest()
        self.reject("foreign separator|starts")

    def test_backslash_path_rejected(self):
        self.manifest["entries"][0]["path"] = "shots\\evil.png"
        self.write_manifest()
        self.reject("foreign separator")

    def test_non_png_path_rejected(self):
        self.manifest["entries"][0]["path"] = "shots/classic.txt"
        self.write_manifest()
        self.reject("must name a .png file")

    def test_symlinked_png_rejected(self):
        target = self.root / "shots" / "classic-1080p.png"
        outside = self.root / "outside.png"
        outside.write_bytes(self.bytes_1080)
        target.unlink()
        target.symlink_to(outside)
        self.reject("symlink")

    def test_symlinked_directory_component_rejected(self):
        real = self.root / "real"
        real.mkdir()
        (real / "classic-1080p.png").write_bytes(self.bytes_1080)
        link = self.root / "shots"
        for child in link.iterdir():
            child.unlink()
        link.rmdir()
        link.symlink_to(real, target_is_directory=True)
        self.manifest["entries"][1]["path"] = "real/classic-1080p.png"
        self.write_manifest()
        self.reject("symlink")

    def test_duplicate_entries_rejected(self):
        entry = dict(self.manifest["entries"][0])
        self.manifest["entries"].append(entry)
        self.write_manifest()
        self.reject("duplicate entry path")

    def test_duplicate_json_object_key_rejected(self):
        raw = json.dumps(self.manifest)
        raw = raw.replace('"manifest_version": 1', '"manifest_version": 1, "manifest_version": 1', 1)
        self.write_manifest(raw)
        self.reject("duplicate JSON key")

    def test_duplicate_entry_json_key_rejected(self):
        raw = json.dumps(self.manifest)
        raw = raw.replace('"width": 1920', '"width": 1920, "width": 1920', 1)
        self.write_manifest(raw)
        self.reject("duplicate JSON key")

    def test_unknown_field_rejected(self):
        self.manifest["execute_script"] = "/bin/sh"
        self.write_manifest()
        self.reject("exactly the required fields")

    def test_missing_field_rejected(self):
        del self.manifest["capture_command"]
        self.write_manifest()
        self.reject("exactly the required fields")

    def test_future_version_rejected(self):
        self.manifest["manifest_version"] = 2
        self.write_manifest()
        self.reject("unsupported manifest_version")

    def test_boolean_version_rejected(self):
        self.manifest["manifest_version"] = True
        self.write_manifest()
        self.reject("unsupported manifest_version")

    def test_bad_commit_rejected(self):
        self.manifest["source_commit"] = "A" * 40
        self.write_manifest()
        self.reject("source_commit")

    def test_boolean_dimension_rejected(self):
        self.manifest["entries"][0]["width"] = True
        self.write_manifest()
        self.reject("positive integer")

    def test_bad_digest_shape_rejected(self):
        self.manifest["entries"][0]["sha256"] = "ABC"
        self.write_manifest()
        self.reject("lowercase 64-hex")

    def test_empty_entries_rejected(self):
        self.manifest["entries"] = []
        self.write_manifest()
        self.reject("non-empty list")

    def test_control_char_in_command_rejected(self):
        self.manifest["capture_command"] = "qt\nrm -rf /"
        self.write_manifest()
        self.reject("clean string")

    def test_manifest_symlink_rejected(self):
        raw = self.manifest_path.read_text(encoding="utf-8")
        real = self.root / "real-manifest.json"
        real.write_text(raw, encoding="utf-8")
        self.manifest_path.unlink()
        self.manifest_path.symlink_to(real)
        self.reject("regular local file")

    def test_manifest_size_is_bounded(self):
        raw = json.dumps(self.manifest)
        self.manifest_path.write_text(raw + " " * 65_537, encoding="utf-8")
        self.reject("exceeds 64 KiB")

    def test_capture_command_is_not_executed(self):
        marker = self.root / "should-not-exist"
        self.manifest["capture_command"] = f"touch {marker}"
        self.write_manifest()
        validate_provenance(self.manifest_path)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
