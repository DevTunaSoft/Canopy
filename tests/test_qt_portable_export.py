"""Guard portable Qt6 export without requiring Qt6 on foundation runners."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/package_qt_runtime.sh"
WORKFLOW = ROOT / ".github/workflows/classic-qt.yml"


class PortableQtExportTests(unittest.TestCase):
    def test_packaging_script_has_valid_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_portable_bundle_does_not_override_host_glibc(self):
        text = SCRIPT.read_text()
        for name in ("libc.so.*", "libm.so.*", "libresolv.so.*",
                     "libpthread.so.*", "ld-linux*.so.*"):
            with self.subTest(name=name):
                self.assertIn(name, text)
        self.assertIn('continue ;;', text)
        self.assertIn('QT_QML_IMPORT_PATH=', text)

    def test_runtime_bundle_is_kept_independent_from_artwork(self):
        text = WORKFLOW.read_text()
        self.assertIn("bash tools/package_qt_runtime.sh", text)
        self.assertIn("canopy-qt6-compiled-runtime", text)
        self.assertNotIn("Canopy_Classic_Exact_Artwork_Runtime.zip", text)

    def test_missing_binary_is_rejected_without_destination(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "bundle"
            result = subprocess.run(["bash", str(SCRIPT),
                                     str(Path(tmp) / "missing-executable"),
                                     str(output)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
