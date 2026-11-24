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
raw_row = bytearray(bytes([0]) + bytes([32, 40, 52, 255]) * width)
pixels = bytes(raw_row) * height
if mode not in ("blank", "single_pixel"):
    pixels = b"".join(
        bytes(bytearray(raw_row[:5]) + bytes([33 + line % 2, 40, 52, 255])
              + raw_row[9:])
        for line in range(height)
    )
if mode == "single_pixel":
    isolated_pixel = bytearray(raw_row)
    isolated_pixel[5] = 33
    pixels = bytes(isolated_pixel) + bytes(raw_row) * (height - 1)
if mode == "transparent_variation":
    transparent_row = bytearray([0])
    for pixel in range(width):
        transparent_row.extend([pixel % 2 * 255, 40, 52, 0])
    pixels = bytes(transparent_row) * height
image_header = chunk(
    b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
)
compressed = b"not a zlib stream" if mode == "corrupt_idat" else zlib.compress(pixels)
image = (b"\\x89PNG\\r\\n\\x1a\\n" + image_header
         + chunk(b"IDAT", compressed) + chunk(b"IEND", b""))
if mode == "missing_chunks":
    image = (b"\\x89PNG\\r\\n\\x1a\\n" + image_header
             + chunk(b"tEXt", b"fixture\\0padding")
             + chunk(b"IEND", b""))
if mode == "symlink_screenshot":
    destination.symlink_to(Path(os.environ["CANOPY_FAKE_QT_TARGET"]))
else:
    destination.write_bytes(b"not a PNG" if mode == "bad_png" else image)
print("SELF_TEST_PASS: all eight exact approved dock PNGs loaded")
if mode == "repeated_marker":
    print("SELF_TEST_PASS: all eight exact approved dock PNGs loaded")
if mode == "detailed_marker":
    print("SELF_TEST_PASS: all eight exact approved dock PNGs loaded count 8 with equal 54px art slots")
if mode == "secret_output":
    print("PRIVATE_TOKEN=sensitive-example")
print("SELF_TEST_PASS: dock icons horizontally/vertically centred")
if mode == "detailed_marker":
    print("SELF_TEST_PASS: dock icons horizontally/vertically centred count 8 with 7px insets")
if mode != "missing_marker":
    print("SELF_TEST_PASS: nonuniform window screenshot captured")
if mode == "detailed_marker":
    print("SELF_TEST_PASS: nonuniform window screenshot captured QSize(1920, 1080) sampled colors 91")
    print("SELF_TEST_PASS: extra unrelated but genuine check passed")
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
        if os.name == "nt" or not os.access(self.binary, os.X_OK):
            self.skipTest("POSIX fake Qt binary not runnable on this host; NOT_RUN")
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

    def test_blank_but_structurally_valid_png_is_not_a_pass(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "blank"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")
        self.assertEqual([row["screenshot_sha256"] for row in report["tests"]],
                         [None] * 3)

    def test_isolated_pixel_does_not_count_as_screenshot_variation(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "single_pixel"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")

    def test_invisible_transparent_rgb_differences_do_not_count(self):
        with patch.dict(os.environ, {
            "CANOPY_FAKE_QT_MODE": "transparent_variation",
        }):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")

    def test_corrupt_idat_stream_is_not_a_pass(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "corrupt_idat"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")

    def test_missing_png_chunks_are_not_a_pass(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "missing_chunks"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")

    def test_repeated_self_test_marker_is_not_a_pass(self):
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "repeated_marker"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")
        self.assertEqual([row["markers_observed"] for row in report["tests"]],
                         [4] * 3)

    @unittest.skipIf(os.name == "nt", "POSIX pipe selector required for Qt smoke")
    def test_detailed_marker_lines_are_accepted(self):
        """Real Qt builds append detail after markers; 19 lines must still pass."""
        with patch.dict(os.environ, {"CANOPY_FAKE_QT_MODE": "detailed_marker"}):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "PASS")
        self.assertTrue(all(row["markers_observed"] >= 3 for row in report["tests"]))

    def test_marker_helper_matches_real_detailed_lines(self):
        prefixes = {b"SELF_TEST_PASS: dock icons horizontally/vertically centred": "dock"}
        line = b"SELF_TEST_PASS: dock icons horizontally/vertically centred count 8 with 7px insets"
        self.assertEqual(smoke._match_marker_line(line, prefixes, set()), ("dock", False))

    def test_marker_helper_rejects_duplicate_exact_line(self):
        prefixes = {b"SELF_TEST_PASS: dock icons horizontally/vertically centred": "dock"}
        line = b"SELF_TEST_PASS: dock icons horizontally/vertically centred"
        seen = set()
        self.assertEqual(smoke._match_marker_line(line, prefixes, seen), ("dock", False))
        self.assertEqual(smoke._match_marker_line(line, prefixes, seen), ("dock", True))

    def test_marker_counted_once_across_base_and_detailed_lines(self):
        prefixes = {b"SELF_TEST_PASS: dock icons horizontally/vertically centred": "dock"}
        counts = {"dock": 0}
        seen, counted = set(), set()
        self.assertFalse(smoke._register_marker(
            b"SELF_TEST_PASS: dock icons horizontally/vertically centred",
            prefixes, seen, counted, counts))
        self.assertFalse(smoke._register_marker(
            b"SELF_TEST_PASS: dock icons horizontally/vertically centred count 8",
            prefixes, seen, counted, counts))
        self.assertEqual(counts["dock"], 1)

    def test_symlinked_screenshot_is_not_hashed_or_reported_as_pass(self):
        target = self.root / "private.png"
        target.write_bytes(b"private screenshot")
        with patch.dict(os.environ, {
            "CANOPY_FAKE_QT_MODE": "symlink_screenshot",
            "CANOPY_FAKE_QT_TARGET": str(target),
        }):
            report = self.run_smoke()
        self.assertEqual(report["qt_smoke"], "FAIL")
        self.assertEqual([row["screenshot_sha256"] for row in report["tests"]],
                         [None] * 3)

    def test_png_crc_tampering_not_reported_valid(self):
        self.run_smoke()
        path = self.out / "qt-760x500.png"
        bits = bytearray(path.read_bytes())
        bits[48] ^= 1
        path.write_bytes(bits)
        with self.assertRaisesRegex(smoke.MintSmokeError, "CRC"):
            smoke.png_size(path)

    def test_truncated_png_does_not_pass(self):
        self.run_smoke()
        path = self.out / "qt-760x500.png"
        path.write_bytes(path.read_bytes()[:-12])
        with self.assertRaises(smoke.MintSmokeError):
            smoke.png_size(path)

    def test_padding_after_iend_is_rejected(self):
        self.run_smoke()
        path = self.out / "qt-760x500.png"
        path.write_bytes(path.read_bytes() + b"padding")
        with self.assertRaisesRegex(smoke.MintSmokeError, "trailing bytes"):
            smoke.png_size(path)

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
        with patch.dict(os.environ, {
            "PRIVATE_TOKEN": "sensitive-example",
            "CANOPY_FAKE_QT_MODE": "secret_output",
        }):
            report = self.run_smoke()
        raw = (self.out / "report.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("PRIVATE_TOKEN", raw)
        self.assertNotIn("sensitive-example", raw)
        self.assertNotIn("DISPLAY", raw)
        self.assertEqual(report["declared_source_sha"], self.source_sha)

    def test_report_writer_does_not_follow_symlink(self):
        self.out.mkdir()
        destination = self.out / "report.json"
        protected = self.root / "protected-report.json"
        protected.write_text("keep", encoding="utf-8")
        destination.symlink_to(protected)
        with self.assertRaises(FileExistsError):
            smoke._write_report(destination, {"private": "do not serialize"})
        self.assertEqual(protected.read_text(encoding="utf-8"), "keep")

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

    def test_output_under_symlinked_parent_is_rejected(self):
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(smoke.MintSmokeError):
            self.run_smoke(out=linked_parent / "evidence")

    def test_symlinked_binary_rejected(self):
        linked = self.root / "fake-qt-link"
        linked.symlink_to(self.binary)
        with self.assertRaisesRegex(smoke.MintSmokeError, "non-symlink"):
            self.run_smoke(binary=linked)
        self.assertFalse(self.out.exists())

    def test_symlinked_resource_parent_is_rejected(self):
        linked_parent = self.root / "linked-assets"
        linked_parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(smoke.MintSmokeError, "non-symlink"):
            self.run_smoke(art=linked_parent / self.art.name)
        self.assertFalse(self.out.exists())

    def test_invalid_source_sha_rejected_before_output(self):
        with self.assertRaisesRegex(smoke.MintSmokeError, "40-character"):
            self.run_smoke(source_sha="unverified")
        self.assertFalse(self.out.exists())

    def test_unreasonable_and_noninteger_timeouts_are_rejected(self):
        for timeout in (31, 10**9, 2.5, True):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(smoke.MintSmokeError, "timeout"):
                    self.run_smoke(timeout=timeout)
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


class WindowsSkipGuardTests(unittest.TestCase):
    def test_run_smoke_skips_when_windows_platform(self):
        case = MintQtSmokeTests("test_three_resolutions_and_hash_evidence")
        case.setUp()
        self.addCleanup(case.doCleanups)
        with patch.object(os, "name", "nt"):
            with self.assertRaises(unittest.SkipTest) as caught:
                case.run_smoke()
        self.assertIn("NOT_RUN", str(caught.exception))


class SymlinkOpenGuardTests(unittest.TestCase):
    def test_open_regular_file_rejects_symlink_without_o_nofollow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "real-report.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "report.json"
            link.symlink_to(target)
            with patch.object(os, "O_NOFOLLOW", 0, create=True):
                with self.assertRaises(smoke.MintSmokeError):
                    with smoke._open_regular_file(link):
                        pass


if __name__ == "__main__":
    unittest.main()
