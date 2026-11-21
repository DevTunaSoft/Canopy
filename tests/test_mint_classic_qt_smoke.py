"""Synthetic Qt stand-ins test the Mint screenshot harness without a real VM.

A green unit test is NOT a Mint GUI validation. Genuine Mint acceptance
requires executing the tool inside an actual Linux Mint guest.
"""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import mint_classic_qt_smoke as smoke


FAKE_QT = '''#!/usr/bin/env python3
import os
from pathlib import Path
import struct
import sys
import time
import zlib

def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
args = sys.argv[1:]
mode = os.environ.get("CANOPY_FAKE_QT_MODE", "good")
if mode == "sleep":
    time.sleep(3)
size = args[args.index("--self-test-size") + 1]
width, height = map(int, size.split("x"))
if mode == "wrong_size":
    width += 1
destination = Path(args[args.index("--self-test-screenshot") + 1])
raw_row = bytes([0]) + bytes([32, 40, 52, 255]) * width
pixels = raw_row * height
image = (b"\\x89PNG\\r\\n\\x1a\\n"
         + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
         + chunk(b"IDAT", zlib.compress(pixels))
         + chunk(b"IEND", b""))
destination.write_bytes(b"not a PNG" if mode == "bad_png" else image)
print("SELF_TEST_PASS: all eight exact approved dock PNGs loaded")
print("SELF_TEST_PASS: dock icons horizontally/vertically centred")
if mode != "missing_marker":
    print("SELF_TEST_PASS: nonuniform window screenshot captured")
if "--icon-framing-review" in args and mode != "missing_frame":
    print("SELF_TEST_PASS: opt-in icon source framing verified")
if mode == "bad_exit":
    sys.exit(4)
'''


class MintQtSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "fake-qt"
        self.binary.write_text(FAKE_QT, encoding="utf-8")
        self.binary.chmod(0o700)
        self.art = self.root / "approved-art"
        self.art.mkdir()
        self.wallpaper = self.root / "alpine.png"
        self.wallpaper.write_bytes(b"test")
        self.terminal = self.root / "terminal.png"
        self.terminal.write_bytes(b"fake")
        self.ready = {"status": "READY_FOR_TESTS", "mint_identified": True}
        self.source_sha = "a" * 40
        self.out = self.root / "qt-evidence"

    def run_smoke(self, **kwargs):
        return smoke.run_mint_smoke(
            binary=kwargs.get("binary", self.binary),
            approved_art=kwargs.get("art", self.art),
            wallpaper=kwargs.get("wallpaper", self.wallpaper),
            output_dir=kwargs.get("out", self.out),
            source_sha=kwargs.get("source_sha", self.source_sha),
            terminal=kwargs.get("terminal"),
            framing_review=kwargs.get("framing", False),
            preflight=kwargs.get("preflight", self.ready),
            timeout_seconds=kwargs.get("timeout", 8),
        )

    def test_three_resolutions_and_hash_evidence(self):
        report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "PASS")
        self.assertEqual(report["mint_guest_acceptance"], "PARTIAL_SMOKE_ONLY")
        self.assertEqual(report["visual_owner_approval"], "NOT_RUN")
        self.assertEqual(report["real_application_launch"], "NOT_RUN")
        self.assertEqual(report["compositor_session_switching"], "NOT_RUN")
        self.assertEqual([row["resolution"] for row in report["tests"]],
                         ["1920x1080", "1200x750", "760x500"])
        self.assertEqual([row["status"] for row in report["tests"]],
                         ["PASS"] * 3)
        for row in report["tests"]:
            self.assertEqual(row["exit_code"], 0)
            self.assertEqual(len(row["screenshot_sha256"]), 64)
            self.assertEqual(
                smoke.png_size(self.out / row["screenshot"]),
                tuple(map(int, row["resolution"].split("x"))),
            )
        self.assertEqual(json.loads((self.out / "report.json").read_text()),
                         report)

    def test_opt_in_framing_requires_matching_qt_marker(self):
        report = self.run_smoke(framing=True, terminal=self.terminal)
        self.assertEqual(report["qt_smoke"], "PASS")
        self.assertTrue(report["framing_review"])
        self.assertFalse(report["visual_owner_approval"] == "PASS")

    def test_no_fake_mint_or_missing_display_preflight(self):
        for preflight in (
            {"status": "BLOCKED", "mint_identified": False},
            {"status": "READY_FOR_TESTS", "mint_identified": False},
            {"status": "BLOCKED", "mint_identified": True},
            {},
        ):
            with self.subTest(preflight=preflight):
                with self.assertRaisesRegex(smoke.MintSmokeError, "Linux Mint"):
                    self.run_smoke(preflight=preflight)
                self.assertFalse(self.out.exists())

    def test_wrong_screenshot_resolution_is_not_a_pass(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "wrong_size"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")
        self.assertEqual([r["status"] for r in report["tests"]], ["FAIL"] * 3)

    def test_corrupted_png_is_not_a_pass(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "bad_png"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")

    def test_missing_actual_qt_marker_is_a_failure(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "missing_marker"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")

    def test_missing_framing_marker_fails_when_requested(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "missing_frame"}):
            report = self.run_smoke(framing=True)
        self.assertEqual(report["qt_smoke"], "FAIL")

    def test_nonzero_exit_is_not_reported_as_success(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "bad_exit"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")
        self.assertEqual([r["exit_code"] for r in report["tests"]], [4, 4, 4])

    def test_timeout_is_failure_not_false_success(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "sleep"}):
            report = self.run_smoke(timeout=2)
        self.assertEqual(report["qt_smoke"], "FAIL")
        self.assertEqual([r["status"] for r in report["tests"]], ["FAIL"] * 3)

    def test_report_does_not_expose_full_asset_paths_or_env_secrets(self):
        with patch.dict(os.environ, {"PRIVATE_TOKEN": "sensitive-example"}):
            report = self.run_smoke()
        raw = (self.out / "report.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("PRIVATE_TOKEN", raw)
        self.assertNotIn("sensitive-example", raw)
        self.assertNotIn("DISPLAY", raw)
        self.assertEqual(report["declared_source_sha"], self.source_sha)

    def test_existing_output_directory_is_never_overwritten(self):
        self.out.mkdir()
        sentinel = self.out / "owner.txt"
        sentinel.write_text("keep")
        with self.assertRaisesRegex(smoke.MintSmokeError, "new absolute directory"):
            self.run_smoke()
        self.assertEqual(sentinel.read_text(), "keep")

    def test_symlinked_output_directory_rejected(self):
        other = self.root / "other"
        other.mkdir()
        self.out.symlink_to(other, target_is_directory=True)
        with self.assertRaises(smoke.MintSmokeError):
            self.run_smoke()
        self.assertEqual(list(other.iterdir()), [])

    def test_symlinked_binary_rejected(self):
        linked = self.root / "fake-qt-link"
        linked.symlink_to(self.binary)
        with self.assertRaisesRegex(smoke.MintSmokeError, "non-symlink"):
            self.run_smoke(binary=linked)
        self.assertFalse(self.out.exists())

    def test_invalid_source_sha_rejected_before_output(self):
        with self.assertRaisesRegex(smoke.MintSmokeError, "40-character"):
            self.run_smoke(source_sha="unverified")
        self.assertFalse(self.out.exists())

    def test_missing_art_directory_rejected(self):
        with self.assertRaises(smoke.MintSmokeError):
            self.run_smoke(art=self.root / "missing-art")
        self.assertFalse(self.out.exists())

    def test_executable_without_execute_bits_is_rejected(self):
        self.binary.chmod(0o600)
        with self.assertRaisesRegex(smoke.MintSmokeError, "not executable"):
            self.run_smoke()
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
