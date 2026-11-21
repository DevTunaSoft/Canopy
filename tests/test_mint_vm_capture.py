"""Host-safe tests for the prepared, not-yet-run Linux Mint VM capture."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/mint_vm_capture.sh"


class MintVmCaptureTests(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_without_side_effects(self):
        result = subprocess.run(["bash", str(SCRIPT), "--help"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone Qt window only", result.stdout)

    def test_fail_closed_outside_mint_and_without_graphical_session(self):
        source = SCRIPT.read_text()
        self.assertIn('"${ID:-}" != "linuxmint"', source)
        self.assertIn('"${DISPLAY:-}"', source)
        self.assertIn('"${WAYLAND_DISPLAY:-}"', source)
        self.assertIn('ARGS=(--landscape-wallpaper "$WALLPAPER")', source)
        self.assertIn("--self-test-launcher-filter-files", source)
        self.assertNotIn("sudo ", source)
        self.assertNotIn("apt-get ", source)
        self.assertNotIn("systemctl ", source)

    def test_resource_sampler_accepts_selected_assets(self):
        sampler = (ROOT / "tools/measure_qt.py").read_text()
        self.assertIn('parser.add_argument("--landscape-wallpaper"', sampler)
        self.assertIn('parser.add_argument("--approved-art-dir"', sampler)
        self.assertIn("subprocess.Popen([str(exe), *app_args]", sampler)
        self.assertIn('"external-landscape"', sampler)


if __name__ == "__main__":
    unittest.main()
