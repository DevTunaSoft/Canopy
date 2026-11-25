"""Five-icon dock gates: bounded frozen jitter, verified v3 pack, CI contracts."""
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
import zlib

from tests.test_classic_icon_frame_diff import make_rgba_png, png_chunk
from tools.check_classic_icon_frame_diff import APPS, CENTERS, ComparisonError
from tools.check_five_dock_centering import (
    FROZEN, FROZEN_JITTER_MAX, TARGET, compare_five, verify_pack_activation
)

ROOT = Path(__file__).resolve().parents[1]
QT = ROOT / "prototype" / "classic"
WORKFLOW = ROOT / ".github" / "workflows" / "classic-qt.yml"
ACCEPTANCE = ROOT / "docs" / "CLASSIC_FIVE_DOCK_PRODUCTION_ACCEPTANCE.md"
V3_PACK_MANIFEST_SHA256 = (
    "df0b7166b0a3269d7f99484d5196633193162eba56b334b25a1ea39f9682a360"
)
CI_V3_PACK_MANIFEST_SHA256 = (
    "3464d1d03648d8f7814f4337174691d874faa4415c38d5c245dc5fe3f09981ac"
)
V3_RENDERER = "canopy-five-qt-v3"


def make_exact_rgba_png(width, height, changes):
    """Build a PNG with explicit RGBA values at the given (x, y) pixels."""
    stride = width * 4
    pixels = bytearray(bytes((25, 35, 45, 255)) * (width * height))
    for (x, y), rgba in changes.items():
        offset = 4 * (y * width + x)
        pixels[offset:offset + 4] = bytes(rgba)
    scanlines = b"".join(
        b"\x00" + pixels[y * stride:(y + 1) * stride]
        for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) +
            png_chunk(b"IDAT", zlib.compress(scanlines)) +
            png_chunk(b"IEND", b""))


class FiveIconSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = (QT / "RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        cls.main = (QT / "main.cpp").read_text(encoding="utf-8")
        cls.header = (QT / "RoundedDockIconProvider.h").read_text(encoding="utf-8")
        cls.centers = CENTERS["760x500"]["desktop"]
        cls.five = [pt for name, pt in zip(APPS, cls.centers) if name in TARGET]

    def test_only_five_optical_offsets_and_three_frozen(self):
        table = self.provider.split("kFiveDockCenterOffsets = {")[1].split("};")[0]
        entries = re.findall(
            r'QStringLiteral\("([a-z]+)"\), QPointF\((-?\d+), (-?\d+)\)', table)
        self.assertEqual(len(entries), 5)
        self.assertEqual({name.title() for name, _, _ in entries}, TARGET)
        self.assertFalse({name.title() for name, _, _ in entries} & FROZEN)
        self.assertTrue(all(abs(int(x)) <= 9 and abs(int(y)) <= 9
                            for _, x, y in entries))
        self.assertIn("kFiveDockCenterOffsets.constFind(id)", self.provider)

    def test_default_runtime_and_exact_rollbacks_are_preserved(self):
        self.assertIn('args.contains(QStringLiteral("--dock-five-center-review"))',
                      self.main)
        self.assertIn("const bool dockFiveCenterModeSelected =", self.main)
        self.assertIn("(dockFiveCenterReviewMode || !dockCleanEdgesReviewMode)",
                      self.main)
        self.assertIn("DOCK_FIVE_CENTER_FAIL", self.main)
        self.assertNotIn("dockFiveCenterReviewMode = true", self.main)
        self.assertIn('bool fiveOnlyCenterReviewMode = false', self.header)
        self.assertIn("if (fiveOnlyCenterReviewMode && !cleanSourceEdgesReviewMode)",
                      self.provider)
        self.assertIn('constexpr auto kPackRenderer = "canopy-five-qt-v3";',
                      self.provider)

    def test_runtime_distinguishes_verified_pack_from_fallback(self):
        self.assertIn('args.contains(QStringLiteral("--require-five-production-icons"))',
                      self.main)
        self.assertIn("FIVE_PRODUCTION_PACK_FAIL: pack absent or SHA-invalid",
                      self.main)
        self.assertIn("FIVE_PRODUCTION_PACK_VERIFIED: exactly five SHA-verified",
                      self.main)
        self.assertIn("FIVE_PRODUCTION_PACK_FALLBACK: exact original-derived",
                      self.main)
        self.assertIn("DOCK_FIVE_CENTER_ACTIVE", self.main)


class FiveIconPixelLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.centers = CENTERS["760x500"]["desktop"]
        cls.five = [pt for name, pt in zip(APPS, cls.centers) if name in TARGET]

    def pair(self, changed):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.png"
            b = Path(d) / "b.png"
            a.write_bytes(make_rgba_png(760, 500))
            b.write_bytes(make_rgba_png(760, 500, changed))
            return compare_five(a, b, "760x500")

    def exact_pair(self, after, before=None, size="760x500"):
        width, height = [int(n) for n in size.split("x")]
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.png"
            b = Path(d) / "b.png"
            a.write_bytes(make_exact_rgba_png(width, height, before or {}))
            b.write_bytes(make_exact_rgba_png(width, height, after))
            return compare_five(a, b, size)

    def target_changes(self, centers=None):
        return {pt: (155, 35, 45, 255)
                for pt in (centers if centers is not None else self.five)}

    def frozen_noise(self, app, count, size="760x500"):
        cx, cy = CENTERS[size]["desktop"][APPS.index(app)]
        before, after = {}, {}
        for i in range(count):
            pt = (cx + 8 + 2 * i, cy + 4)
            before[pt] = (156, 175, 183, 255)
            after[pt] = (155, 175, 183, 255)
        return before, after

    def test_frozen_identity_mode_accepts_identical_v3_captures(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "default.png"
            b = Path(d) / "explicit.png"
            a.write_bytes(make_exact_rgba_png(760, 500, {}))
            b.write_bytes(make_exact_rgba_png(760, 500, {}))
            result = compare_five(a, b, "760x500", frozen_identity=True)
            self.assertTrue(result["frozen_identity_mode"])
            self.assertFalse(result["target_change_required"])
            self.assertIsNone(result["five_targets_genuinely_changed"])
            self.assertTrue(result["calendar_photos_music_pixel_perfect"])

    def test_frozen_identity_still_rejects_artwork_and_non_icon_changes(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "default.png"
            b = Path(d) / "explicit.png"
            a.write_bytes(make_exact_rgba_png(760, 500, {}))
            frozen = CENTERS["760x500"]["desktop"][APPS.index("Photos")]
            with self.subTest(case="frozen"):
                b.write_bytes(make_exact_rgba_png(
                    760, 500, {frozen: (155, 35, 45, 255)}))
                with self.assertRaisesRegex(ComparisonError, "frozen Photos"):
                    compare_five(a, b, "760x500", frozen_identity=True)
            with self.subTest(case="non-icon"):
                b.write_bytes(make_exact_rgba_png(
                    760, 500, {(20, 200): (155, 35, 45, 255)}))
                with self.assertRaisesRegex(ComparisonError, "unexpected non-icon"):
                    compare_five(a, b, "760x500", frozen_identity=True)

    def test_five_changes_and_clock_allowed(self):
        result = self.pair(self.five + [(750, 10)])
        self.assertTrue(result["calendar_photos_music_pixel_perfect"])
        self.assertTrue(result["five_targets_genuinely_changed"])
        self.assertEqual(result["clock_exception_pixels"], 1)
        self.assertEqual(result["non_icon_changes"], 0)

    def test_calendar_photos_music_change_rejected(self):
        for name in FROZEN:
            index = APPS.index(name)
            with self.subTest(name=name), self.assertRaisesRegex(
                    ComparisonError, "frozen"):
                self.pair(self.five + [self.centers[index]])

    def test_missing_target_or_unexpected_pixel_fails(self):
        for k in range(5):
            with self.subTest(k=k), self.assertRaisesRegex(
                    ComparisonError, "did not change"):
                self.pair(self.five[:k] + self.five[k + 1:])
        with self.assertRaisesRegex(ComparisonError, "unexpected non-icon"):
            self.pair(self.five + [(20, 200)])
        with self.assertRaisesRegex(ComparisonError, "unsupported"):
            compare_five(Path("missing"), Path("missing"), "640x480")

    def test_one_level_frozen_noise_within_bound_is_recorded_not_rejected(self):
        before, noise = self.frozen_noise("Photos", FROZEN_JITTER_MAX)
        after = self.target_changes()
        after.update(noise)
        result = self.exact_pair(after, before)
        self.assertEqual(result["frozen_one_level_compositing_jitter"]["Photos"],
                         FROZEN_JITTER_MAX)
        self.assertEqual(result["one_level_dock_plate_aa_pixels"],
                         FROZEN_JITTER_MAX)
        self.assertTrue(result["calendar_photos_music_pixel_perfect"])
        self.assertTrue(result["five_targets_genuinely_changed"])

    def test_ci_sized_one_level_frozen_noise_is_not_artwork_change(self):
        # Bounded compositing noise near the Photos and Calendar slot centers
        # of the authoritative 1200x750 Xvfb capture, with all five targets
        # genuinely changed. This is a negative control for the false
        # FIVE_DOCK_ICON_PIXEL_LOCK_FAIL that motivated the exception.
        size = "1200x750"
        centers = [pt for name, pt in zip(APPS, CENTERS[size]["desktop"])
                   if name in TARGET]
        after = self.target_changes(centers)
        before = {}
        for app, dx, dy, red in (("Photos", 20, 4, 156),
                                 ("Photos", 20, 9, 162),
                                 ("Calendar", 14, 4, 157)):
            cx, cy = CENTERS[size]["desktop"][APPS.index(app)]
            pt = (cx + dx, cy + dy)
            before[pt] = (red, 175, 183, 255)
            after[pt] = (red - 1, 175, 183, 255)
        result = self.exact_pair(after, before, size)
        self.assertEqual(result["frozen_one_level_compositing_jitter"],
                         {"Calendar": 1, "Photos": 2, "Music": 0})
        self.assertEqual(result["one_level_dock_plate_aa_pixels"], 3)
        self.assertTrue(result["calendar_photos_music_pixel_perfect"])
        self.assertTrue(result["five_targets_genuinely_changed"])

    def test_frozen_slot_larger_delta_alpha_and_excess_noise_still_fail(self):
        cx, cy = CENTERS["760x500"]["desktop"][APPS.index("Photos")]
        for label, rgba in (("two levels", (157, 35, 45, 255)),
                            ("alpha shift", (25, 35, 45, 254))):
            after = self.target_changes()
            after[(cx + 10, cy + 5)] = rgba
            with self.subTest(case=label), self.assertRaisesRegex(
                    ComparisonError, "frozen Photos"):
                self.exact_pair(after)
        before, noise = self.frozen_noise("Photos", FROZEN_JITTER_MAX + 1)
        after = self.target_changes()
        after.update(noise)
        with self.assertRaisesRegex(ComparisonError, "frozen Photos"):
            self.exact_pair(after, before)

    def test_noise_exception_does_not_excuse_missing_target_or_other_changes(self):
        before, noise = self.frozen_noise("Photos", 2)
        after = self.target_changes()
        del after[self.five[0]]
        after.update(noise)
        with self.assertRaisesRegex(ComparisonError, "did not change"):
            self.exact_pair(after, before)
        after = self.target_changes()
        after.update(noise)
        after[(20, 200)] = (155, 35, 45, 255)
        with self.assertRaisesRegex(ComparisonError, "unexpected non-icon"):
            self.exact_pair(after, before)


class VerifiedProductionPackActivationTests(unittest.TestCase):
    def test_verified_log_is_accepted(self):
        log = ("CANOPY_APPROVED_ART_VERIFIED\n"
               "DOCK_FIVE_CENTER_ACTIVE: Browser, Mail, Files, Terminal, Settings\n"
               "FIVE_PRODUCTION_PACK_VERIFIED: exactly five SHA-verified icons\n")
        result = verify_pack_activation(log)
        self.assertEqual(result["FIVE_PRODUCTION_PACK_VERIFIED"], 1)
        self.assertEqual(result["fallback_count"], 0)
        self.assertEqual(result["renderer"], V3_RENDERER)

    def test_fallback_fail_missing_and_duplicate_markers_fail_closed(self):
        verified = "FIVE_PRODUCTION_PACK_VERIFIED: exactly five SHA-verified icons\n"
        cases = {
            "fallback": verified + "FIVE_PRODUCTION_PACK_FALLBACK: renderer\n",
            "fail": verified + "FIVE_PRODUCTION_PACK_FAIL: pack absent or SHA-invalid\n",
            "missing": "DOCK_FIVE_CENTER_ACTIVE: no pack\n",
            "duplicate": verified + verified,
            "fallback only": "FIVE_PRODUCTION_PACK_FALLBACK: renderer\n",
        }
        for label, text in cases.items():
            with self.subTest(case=label), self.assertRaisesRegex(
                    ComparisonError, "FIVE_PRODUCTION_PACK_NOT_VERIFIED"):
                verify_pack_activation(text)
        with self.assertRaises(ComparisonError):
            verify_pack_activation(None)

    def test_cli_writes_activation_report_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "runtime.log"
            report = Path(d) / "activation.json"
            log.write_text(
                "FIVE_PRODUCTION_PACK_VERIFIED: exactly five SHA-verified icons\n",
                encoding="utf-8")
            self.assertEqual(0, __import__("tools.check_five_dock_centering",
                                           fromlist=["main"]).main(
                ["--pack-log", str(log), "--output", str(report)]))
            self.assertEqual(1, json.loads(report.read_text(encoding="utf-8"))[
                "FIVE_PRODUCTION_PACK_VERIFIED"])
            log.write_text("FIVE_PRODUCTION_PACK_FALLBACK: renderer\n",
                           encoding="utf-8")
            self.assertEqual(1, __import__("tools.check_five_dock_centering",
                                           fromlist=["main"]).main(
                ["--pack-log", str(log), "--output", str(report)]))


class CiPackStagingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.acceptance = ACCEPTANCE.read_text(encoding="utf-8")

    def test_ci_exports_validates_and_stages_the_v3_pack(self):
        wf = self.workflow
        self.assertIn("--export-five-production-icons build/classic/production-icons", wf)
        self.assertIn("tools/validate_five_production_icons.py", wf)
        self.assertIn("--production-dir build/classic/production-icons", wf)
        self.assertIn("diff -r build/classic/production-icons "
                      "test-artifacts/reproducible-five-icons", wf)
        self.assertIn("production-icons/manifest.json", wf)
        self.assertIn("sha256sum build/classic/production-icons/manifest.json", wf)
        self.assertIn(CI_V3_PACK_MANIFEST_SHA256, wf)
        self.assertIn("| sha256sum -c -", wf)

    def test_ci_verifies_default_activation_identity_not_a_widened_rectangle(self):
        wf = self.workflow
        self.assertIn("--frozen-identity", wf)
        self.assertIn('--before "test-artifacts/classic-$size.png"', wf)
        self.assertIn("dock-five-center-identity-$size.json", wf)
        self.assertNotIn("--dock-clean-edges-review", wf)

    def test_ci_requires_verified_runtime_and_rejects_fallback(self):
        wf = self.workflow
        self.assertIn("--require-five-production-icons", wf)
        self.assertIn("--pack-log test-artifacts/five-production-runtime.log", wf)
        self.assertIn("FIVE_PRODUCTION_PACK_VERIFIED=1", wf)
        self.assertIn("tools.check_five_dock_centering", wf)
        # A staged log check must explicitly reject a fallback verdict.
        self.assertIn("verify_pack_activation", wf)

    def test_acceptance_doc_records_bounded_jitter_not_zero_pixels(self):
        doc = self.acceptance
        self.assertIn("bounded one-level compositing jitter", doc)
        self.assertIn("FROZEN_JITTER_MAX", doc)
        self.assertNotIn("rejects even **one changed", doc)
        self.assertNotIn("rejects even one changed", doc)
        self.assertIn(V3_PACK_MANIFEST_SHA256, doc)
        self.assertIn(V3_RENDERER, doc)


if __name__ == "__main__":
    unittest.main()
