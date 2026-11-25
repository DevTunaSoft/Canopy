"""Five-only Canopy Classic dock centering: explicit no-touch contracts."""
from pathlib import Path
import re
import struct
import tempfile
import unittest
import zlib

from tests.test_classic_icon_frame_diff import make_rgba_png, png_chunk
from tools.check_classic_icon_frame_diff import APPS, CENTERS, ComparisonError
from tools.check_five_dock_centering import (
    FROZEN, FROZEN_JITTER_MAX, TARGET, compare_five
)

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"



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
    return (b"\x89PNG\r\n\x1a\n" +
            png_chunk(b"IHDR", ihdr) +
            png_chunk(b"IDAT", zlib.compress(scanlines)) +
            png_chunk(b"IEND", b""))

class FiveIconCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = (ROOT / "RoundedDockIconProvider.cpp").read_text()
        cls.main = (ROOT / "main.cpp").read_text()
        cls.h = (ROOT / "RoundedDockIconProvider.h").read_text()
        cls.qml = (ROOT / "DockTile.qml").read_text()
        cls.centers = CENTERS["760x500"]["desktop"]
        cls.five = [pt for name,pt in zip(APPS,cls.centers) if name in TARGET]

    def test_only_five_optical_offsets_and_three_exactly_frozen(self):
        table = self.p.split("kFiveDockCenterOffsets = {")[1].split("};")[0]
        entries = re.findall(r'QStringLiteral\("([a-z]+)"\), QPointF\((-?\d+), (-?\d+)\)',table)
        self.assertEqual(len(entries),5)
        self.assertEqual({name.title() for name,x,y in entries},TARGET)
        self.assertFalse({name.title() for name,x,y in entries} & FROZEN)
        self.assertTrue(all(abs(int(x))<=9 and abs(int(y))<=9 for name,x,y in entries))
        self.assertIn("const auto center = kFiveDockCenterOffsets.constFind(id)",self.p)
        self.assertIn("if (center != kFiveDockCenterOffsets.cend())",self.p)
        self.assertIn("artwork.translate(delta);",self.p)
        self.assertIn("painter.drawImage(artwork, source)",self.p)
        self.assertIn("painter.drawImage(face, edgeFill)",self.p)

    def test_opt_in_and_source_integrity_required(self):
        self.assertIn('args.contains(QStringLiteral("--dock-five-center-review"))',self.main)
        self.assertIn("if (dockFiveCenterReviewMode && !approvedMode)",self.main)
        self.assertIn("DOCK_FIVE_CENTER_FAIL",self.main)
        self.assertIn("bool fiveOnlyCenterReviewMode = false",self.h)
        self.assertIn("if (fiveOnlyCenterReviewMode && !cleanSourceEdgesReviewMode)",self.p)
        self.assertIn("dockCleanEdgesReviewModeSelected, dockFiveCenterModeSelected",self.main)
        self.assertIn("const bool dockFiveCenterModeSelected =", self.main)
        self.assertIn("(dockFiveCenterReviewMode || !dockCleanEdgesReviewMode)", self.main)
        self.assertIn("if (dockFiveCenterModeSelected)", self.main)
        self.assertNotIn("dockFiveCenterReviewMode = true",self.main)
        self.assertIn("SELF_TEST_PASS: five icons optically centered",self.main)

    def test_pngs_qml_and_frozen_geometry_unchanged(self):
        self.assertIn("anchors.centerIn: parent",self.qml)
        self.assertIn("width: 62",self.qml)
        self.assertIn("height: 62",self.qml)
        self.assertNotIn("QImageWriter",self.p)
        self.assertNotIn("QFile::remove(",self.p)
        self.assertNotIn("painter.translate(",self.p)
        self.assertNotIn("QTimer",self.p)

    def pair(self, changed):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/"a.png"; b=Path(d)/"b.png"
            a.write_bytes(make_rgba_png(760,500))
            b.write_bytes(make_rgba_png(760,500,changed))
            return compare_five(a,b,"760x500")

    def test_five_changes_and_clock_allowed(self):
        result=self.pair(self.five+[(750,10)])
        self.assertTrue(result["calendar_photos_music_pixel_perfect"])
        self.assertTrue(result["five_targets_genuinely_changed"])
        self.assertEqual(result["clock_exception_pixels"],1)
        self.assertEqual(result["non_icon_changes"],0)

    def test_calendar_photos_music_change_rejected(self):
        for name in FROZEN:
            index=APPS.index(name)
            with self.subTest(name=name), self.assertRaisesRegex(ComparisonError,"frozen"):
                self.pair(self.five+[self.centers[index]])

    def test_missing_target_or_unexpected_pixel_fails(self):
        for k in range(5):
            with self.subTest(k=k), self.assertRaisesRegex(ComparisonError,"did not change"):
                self.pair(self.five[:k]+self.five[k+1:])
        with self.assertRaisesRegex(ComparisonError,"unexpected non-icon"):
            self.pair(self.five+[(20,200)])
        with self.assertRaisesRegex(ComparisonError,"unsupported"):
            self.pair(self.five) if False else compare_five(
                Path("missing"),Path("missing"),"640x480")

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
        before = {}
        after = {}
        for i in range(count):
            pt = (cx + 8 + 2 * i, cy + 4)
            before[pt] = (156, 175, 183, 255)
            after[pt] = (155, 175, 183, 255)
        return before, after

    def test_ci_1200x750_one_level_photos_noise_is_not_artwork_change(self):
        # Exact failing pixels from CI run 45561718087 attempt 1: four
        # Photos pixels changed by one red level and one Calendar pixel
        # likewise. The docs-only PR changed no source, QML or asset file.
        centers = [pt for name, pt in zip(APPS, CENTERS["1200x750"]["desktop"])
                   if name in TARGET]
        after = self.target_changes(centers)
        before = {}
        for x, y, red in ((666, 686, 156), (666, 691, 162),
                            (641, 707, 157), (641, 708, 155),
                            (564, 685, 156)):
            before[(x, y)] = (red, 175, 183, 255)
            after[(x, y)] = (red - 1, 175, 183, 255)
        result = self.exact_pair(after, before, "1200x750")
        self.assertEqual(result["frozen_one_level_compositing_jitter"],
                         {"Calendar": 1, "Photos": 4, "Music": 0})
        self.assertEqual(result["one_level_dock_plate_aa_pixels"], 5)
        self.assertTrue(result["calendar_photos_music_pixel_perfect"])
        self.assertTrue(result["five_targets_genuinely_changed"])

    def test_frozen_one_level_noise_within_bound_is_recorded_not_rejected(self):
        before, noise = self.frozen_noise("Photos", FROZEN_JITTER_MAX)
        after = self.target_changes()
        after.update(noise)
        result = self.exact_pair(after, before)
        self.assertEqual(result["frozen_one_level_compositing_jitter"]["Photos"],
                         FROZEN_JITTER_MAX)
        self.assertTrue(result["calendar_photos_music_pixel_perfect"])

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


if __name__ == "__main__":
    unittest.main()
