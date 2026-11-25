"""Guard optional Terminal-only art experiments without changing eight masters."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"


class TerminalCandidateTests(unittest.TestCase):
    def test_candidate_requires_validated_originals(self):
        cpp = (CLASSIC / "main.cpp").read_text()
        self.assertIn('QStringLiteral("--terminal-refinement")', cpp)
        self.assertIn('TERMINAL_REFINEMENT_FAIL:', cpp)
        self.assertIn('TERMINAL_REFINEMENT_FAIL: image lacks transparent corners', cpp)
        self.assertLess(cpp.index('verifyExactArtwork(requested, !landscapeMode, &error)'),
                        cpp.index('const QFileInfo candidate(args.at(terminalRefinementIndex + 1))'))
        self.assertLess(cpp.index('CANOPY_TERMINAL_CANDIDATE_VERIFIED'),
                        cpp.index('QQmlApplicationEngine engine;'))
        self.assertIn('seven original dock PNGs plus one Terminal candidate loaded', cpp)

    def test_only_terminal_can_be_replaced(self):
        provider = (CLASSIC / "RoundedDockIconProvider.cpp").read_text()
        self.assertIn('id == QStringLiteral("terminal") && !terminalCandidatePath.isEmpty()', provider)
        self.assertIn('root.filePath(relative)', provider)
        self.assertIn('QImageReader reader(sourcePath)', provider)
        self.assertEqual(provider.count('id == QStringLiteral("terminal")'), 1)
        self.assertIn('painter.setClipPath(outline)', provider)
        self.assertIn('Qt::KeepAspectRatio', provider)
        self.assertNotIn('QFile::remove', provider)
        self.assertNotIn('QImage::save', provider)

    def test_original_art_hash_lock_remains_embedded(self):
        cmake = (CLASSIC / "CMakeLists.txt").read_text()
        cpp = (CLASSIC / "main.cpp").read_text()
        self.assertIn('assets/approved/manifest.json', cmake)
        self.assertIn('QCryptographicHash::Sha256', cpp)
        self.assertIn('SELF_TEST_PASS: all eight exact approved dock PNGs loaded', cpp)


if __name__ == "__main__":
    unittest.main()
