"""Regression and malicious-input controls for the non-destructive optics audit."""

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from tools.audit_approved_icon_optics import (
    AuditError, audit_art, decode_rgba_png, edge_centroid,
)


ROOT = Path(__file__).resolve().parents[1]
NAMES = ("Browser", "Mail", "Files", "Calendar",
         "Photos", "Music", "Terminal", "Settings")


def _chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def make_rgba_png(width=48, height=48, *, at_x=12, filter_type=0):
    """Create a valid sample with a concentrated foreground rectangle."""
    rows = []
    previous = bytearray(width * 4)
    for y in range(height):
        row = bytearray()
        for x in range(width):
            bright = 7 <= x - at_x <= 12 and 13 <= y <= 32
            row.extend((245, 247, 252, 255) if bright else (16, 16, 20, 255))
        if filter_type == 1:
            encoded = bytes(
                (row[i] - (row[i - 4] if i >= 4 else 0)) & 255
                for i in range(len(row))
            )
        elif filter_type == 2:
            encoded = bytes((row[i] - previous[i]) & 255
                            for i in range(len(row)))
        elif filter_type == 3:
            encoded = bytes(
                (row[i] - ((row[i - 4] if i >= 4 else 0) + previous[i]) // 2) & 255
                for i in range(len(row))
            )
        elif filter_type == 4:
            encoded = bytearray()
            for i in range(len(row)):
                a = row[i - 4] if i >= 4 else 0
                b = previous[i]
                c = previous[i - 4] if i >= 4 else 0
                p = a + b - c
                distances = (abs(p - a), abs(p - b), abs(p - c))
                encoded.append((row[i] - (a, b, c)[distances.index(min(distances))]) & 255)
            encoded = bytes(encoded)
        else:
            encoded = bytes(row)
        rows.append(bytes([filter_type]) + encoded)
        previous = row
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB",
                                      width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + _chunk(b"IEND", b"")
    )


class ApprovedOpticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "approved"
        (self.root / "icons").mkdir(parents=True)
        self.manifest_path = Path(self.temp.name) / "manifest.json"
        self.rows = []
        for name in NAMES:
            path = self.root / "icons" / (name + ".png")
            data = make_rgba_png()
            path.write_bytes(data)
            self.rows.append({
                "name": name,
                "path": "icons/" + name + ".png",
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        self.save_manifest()

    def save_manifest(self):
        self.manifest_path.write_text(
            json.dumps({"schema_version": 1, "icons": self.rows}),
            encoding="utf-8",
        )

    def test_png_decoder_reconstructs_all_filters(self):
        for number in range(5):
            with self.subTest(filter=number):
                data = make_rgba_png(filter_type=number)
                width, height, rgba = decode_rgba_png(data)
                self.assertEqual((width, height), (48, 48))
                self.assertEqual(rgba[3], 255)
                self.assertEqual(rgba[(20 * 48 + 22) * 4], 245)
                self.assertEqual(rgba[0], 16)

    def test_crc_tamper_detected(self):
        data = bytearray(make_rgba_png())
        data[-5] ^= 1
        with self.assertRaises(AuditError):
            decode_rgba_png(bytes(data))

    def test_truncated_png_detected(self):
        with self.assertRaises(AuditError):
            decode_rgba_png(make_rgba_png()[:-8])

    def test_invalid_depth_detected(self):
        data = make_rgba_png()
        # Rebuild header chunk so the depth is invalid, with an intact CRC.
        header = bytearray(struct.pack(">IIBBBBB", 48, 48, 16, 6, 0, 0, 0))
        invalid = data[:8] + _chunk(b"IHDR", header) + data[33:]
        with self.assertRaisesRegex(AuditError, "unsupported"):
            decode_rgba_png(invalid)

    def test_saliency_detects_shifted_subject(self):
        width, height, rgba = decode_rgba_png(make_rgba_png(at_x=20))
        result = edge_centroid(width, height, rgba)
        self.assertGreater(result["offset_x_percent"], 5)
        width, height, rgba = decode_rgba_png(make_rgba_png(at_x=2))
        result = edge_centroid(width, height, rgba)
        self.assertLess(result["offset_x_percent"], -5)

    def test_plain_image_has_no_measurable_detail(self):
        constant = bytearray(b"\x10\x10\x10\xff" * (48 * 48))
        with self.assertRaises(AuditError):
            edge_centroid(48, 48, constant)

    def test_audits_eight_locked_icons_without_mutating(self):
        before = {
            row["path"]: (self.root / row["path"]).read_bytes()
            for row in self.rows
        }
        results = audit_art(self.root, self.manifest_path)
        self.assertEqual(len(results["icons"]), 8)
        self.assertTrue(results["all_sha256_verified"])
        self.assertTrue(results["source_bytes_unchanged"])
        self.assertTrue(results["human_visual_approval_required"])
        for path, bytes_before in before.items():
            self.assertEqual((self.root / path).read_bytes(), bytes_before)

    def test_bad_sha_rejected(self):
        first = self.root / self.rows[0]["path"]
        first.write_bytes(make_rgba_png(at_x=4))
        with self.assertRaisesRegex(AuditError, "SHA-256 mismatch"):
            audit_art(self.root, self.manifest_path)

    def test_missing_image_rejected(self):
        (self.root / self.rows[0]["path"]).unlink()
        with self.assertRaisesRegex(AuditError, "missing"):
            audit_art(self.root, self.manifest_path)

    def test_symlink_image_rejected(self):
        path = self.root / self.rows[0]["path"]
        path.unlink()
        path.symlink_to(self.root / self.rows[1]["path"])
        with self.assertRaisesRegex(AuditError, "linked"):
            audit_art(self.root, self.manifest_path)

    def test_symlink_directory_rejected(self):
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(AuditError, "regular paths"):
            audit_art(alias, self.manifest_path)

    def test_path_traversal_rejected(self):
        self.rows[0]["path"] = "icons/../secrets.png"
        self.save_manifest()
        with self.assertRaisesRegex(AuditError, "invalid or duplicated"):
            audit_art(self.root, self.manifest_path)

    def test_duplicate_source_id_rejected(self):
        self.rows[1]["name"] = self.rows[0]["name"]
        self.save_manifest()
        with self.assertRaisesRegex(AuditError, "invalid or duplicated"):
            audit_art(self.root, self.manifest_path)

    def test_duplicate_source_path_rejected(self):
        self.rows[1]["path"] = self.rows[0]["path"]
        self.save_manifest()
        with self.assertRaisesRegex(AuditError, "invalid or duplicated"):
            audit_art(self.root, self.manifest_path)

    def test_manifest_shape_rejected(self):
        self.rows.pop()
        self.save_manifest()
        with self.assertRaisesRegex(AuditError, "exactly eight"):
            audit_art(self.root, self.manifest_path)

    def test_cli_emits_json_report(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "audit_approved_icon_optics.py"),
             "--approved-art-dir", str(self.root),
             "--manifest", str(self.manifest_path)],
            capture_output=True, text=True, check=False,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout)["icons"]), 8)

    def test_cli_bad_input_does_not_write_report(self):
        output = Path(self.temp.name) / "no-report.json"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "audit_approved_icon_optics.py"),
             "--approved-art-dir", str(self.root / "missing"),
             "--manifest", str(self.manifest_path), "--output", str(output)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("CANOPY_ICON_OPTICS_FAIL", proc.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
