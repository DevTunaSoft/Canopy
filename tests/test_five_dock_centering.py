"""Five-only Canopy Classic dock centering: explicit no-touch contracts."""
from pathlib import Path
import re
import tempfile
import unittest

from tests.test_classic_icon_frame_diff import make_rgba_png
from tools.check_classic_icon_frame_diff import APPS, CENTERS, ComparisonError
from tools.check_five_dock_centering import FROZEN, TARGET, compare_five

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"


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
        self.assertIn("dockCleanEdgesReviewModeSelected, dockFiveCenterReviewMode",self.main)
        self.assertNotIn("dockFiveCenterReviewMode = true",self.main)
        self.assertIn("SELF_TEST_PASS: five icons optically centered",self.main)

    def test_pngs_qml_and_frozen_geometry_unchanged(self):
        self.assertIn("anchors.centerIn: parent",self.qml)
        self.assertIn("width: 54",self.qml)
        self.assertIn("height: 54",self.qml)
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


if __name__ == "__main__":
    unittest.main()
