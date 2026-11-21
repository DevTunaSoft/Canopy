"""Synthetic PNG contract tests only: NEVER claim real Mint guest execution."""
import copy
import hashlib
import os
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools import mint_acceptance_report_gate as gate
from tools import mint_classic_qt_smoke as smoke

SOURCE = "a" * 40
BINARY = "b" * 64


def chunk(name, payload):
    return (struct.pack(">I", len(payload)) + name + payload +
            struct.pack(">I", zlib.crc32(name + payload) & 0xffffffff))


def valid_visual_png(width, height):
    # Both horizontal and vertical visible variation; no mock of decoder.
    left = width // 2
    pixels = b"".join(
        b"\x00" + bytes((30 + y % 2, 40, 52)) * left
        + bytes((55 + y % 2, 40, 52)) * (width - left)
        for y in range(height)
    )
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels, 4)) +
            chunk(b"IEND", b""))


class MintEvidenceGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="canopy-mint-gate-tests-")
        cls.directory = Path(cls.tmp.name)
        cls.rows = []
        for w, h in smoke.SIZES:
            label = f"{w}x{h}"
            filename = f"qt-{label}.png"
            data = valid_visual_png(w, h)
            (cls.directory / filename).write_bytes(data)
            cls.rows.append({
                "resolution": label, "status": "PASS",
                "screenshot": filename,
                "screenshot_sha256": hashlib.sha256(data).hexdigest(),
                "exit_code": 0, "markers_observed": 3,
            })
        cls.original = {
            "schema_version": 1, "environment": "linuxmint",
            "qt_smoke": "PASS", "mint_guest_acceptance": "PARTIAL_SMOKE_ONLY",
            "real_application_launch": "NOT_RUN",
            "compositor_session_switching": "NOT_RUN",
            "visual_owner_approval": "NOT_RUN",
            "declared_source_sha": SOURCE, "verified_binary_sha256": BINARY,
            "framing_review": False, "tests": cls.rows,
        }

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.report = copy.deepcopy(self.original)
        self.write_report()

    def write_report(self):
        (self.directory / "report.json").write_text(json.dumps(self.report), encoding="utf-8")

    def check(self, source=SOURCE, binary=BINARY):
        return gate.validate(self.directory, expected_source_sha=source,
                             expected_binary_sha256=binary)

    def test_valid_evidence_passes_integrity_but_not_guest_acceptance(self):
        evidence = self.check()
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["screenshots_verified"], 3)
        self.assertIs(evidence["linux_mint_execution_independently_proven"], False)
        self.assertEqual(evidence["owner_visual_approval"], "NOT_ESTABLISHED")

    def test_wrong_immutable_source_or_binary_pin_fails_closed(self):
        for source, binary in (("c" * 40, BINARY), (SOURCE, "c" * 64),
                               ("../untrusted", BINARY), (SOURCE, "x")):
            with self.subTest(source=source[:8], binary=binary[:8]):
                with self.assertRaises(gate.EvidenceError):
                    self.check(source, binary)

    def test_missing_or_duplicate_resolutions_rejected(self):
        self.report["tests"] = self.rows[:2]
        self.write_report()
        with self.assertRaisesRegex(gate.EvidenceError, "three-resolution"):
            self.check()
        self.report["tests"] = [copy.deepcopy(self.rows[0])] * 3
        self.write_report()
        with self.assertRaisesRegex(gate.EvidenceError, "duplicate"):
            self.check()

    def test_false_green_and_fake_owner_approval_rejected(self):
        for key, value in (("qt_smoke", "FAIL"),
                           ("mint_guest_acceptance", "FULL_ACCEPTANCE"),
                           ("visual_owner_approval", "PASS"),
                           ("real_application_launch", "PASS")):
            with self.subTest(key=key):
                self.report[key] = value
                self.write_report()
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.report[key] = self.original[key]

    def test_fabricated_marker_count_and_boolean_exit_rejected(self):
        for field, value in (("markers_observed", 999), ("exit_code", True),
                             ("screenshot_sha256", "0" * 64),
                             ("screenshot", "../sneaky.png")):
            with self.subTest(field=field):
                self.report["tests"][0][field] = value
                self.write_report()
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.report["tests"][0][field] = self.original["tests"][0][field]

    def test_missing_or_extra_report_fields_rejected(self):
        self.report["injected_secret"] = "should never be accepted"
        self.write_report()
        with self.assertRaisesRegex(gate.EvidenceError, "schema"):
            self.check()

    @unittest.skipIf(os.name == "nt", "POSIX symlink policy is not portable to Windows")
    def test_missing_image_and_symlinked_image_rejected(self):
        target = self.directory / self.rows[0]["screenshot"]
        backup = target.with_suffix(".saved")
        target.rename(backup)
        try:
            with self.assertRaises(gate.EvidenceError):
                self.check()
            target.symlink_to(backup)
            with self.assertRaises(gate.EvidenceError):
                self.check()
        finally:
            if target.is_symlink():
                target.unlink()
            backup.rename(target)

    def test_corrupt_png_rejected_despite_matching_reported_sha(self):
        target = self.directory / self.rows[0]["screenshot"]
        saved = target.read_bytes()
        try:
            corrupt = bytearray(saved)
            corrupt[29] ^= 0x80  # IHDR CRC will no longer match
            target.write_bytes(corrupt)
            self.report["tests"][0]["screenshot_sha256"] = hashlib.sha256(corrupt).hexdigest()
            self.write_report()
            with self.assertRaisesRegex(gate.EvidenceError, "corrupt screenshot"):
                self.check()
        finally:
            target.write_bytes(saved)

    @unittest.skipIf(os.name == "nt", "POSIX symlink policy is not portable to Windows")
    def test_linked_report_rejected(self):
        path = self.directory / "report.json"
        other = self.directory / "other.json"
        path.rename(other)
        try:
            path.symlink_to(other)
            with self.assertRaises(smoke.MintSmokeError):
                self.check()
        finally:
            path.unlink()
            other.rename(path)

    def test_reject_nan_and_blank_report(self):
        path = self.directory / "report.json"
        path.write_text('{"schema_version": NaN}', encoding="utf-8")
        with self.assertRaises(gate.EvidenceError):
            self.check()
        path.write_bytes(b"")
        with self.assertRaises(gate.EvidenceError):
            self.check()


if __name__ == "__main__":
    unittest.main()
