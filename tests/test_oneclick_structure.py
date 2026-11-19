"""Guard against accidental duplicate Windows launcher bodies and recovery functions."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "Canopy-OneClick.ps1"


class OneClickStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = LAUNCHER.read_text(encoding="utf-8-sig")

    def test_unique_function_declarations(self):
        names = re.findall(r"(?im)^function\s+([\w-]+)\b", self.source)
        self.assertEqual(len(names), len(set(name.lower() for name in names)),
                         "Duplicate PowerShell function declarations")

    def test_unique_installation_phases(self):
        for marker in (
            "function Register-CanopyResume {",
            "function Clear-CanopyResume {",
            "function Test-WslReady {",
            "$directory = Join-Path $base 'prepared'",
            "$action = Get-VMAction",
        ):
            with self.subTest(marker=marker):
                self.assertEqual(self.source.count(marker), 1)

    def test_no_code_after_final_launch_status(self):
        marker = "'VM launched; actual Mint installation and desktop boot remain unverified.'"
        self.assertEqual(self.source.count(marker), 1)
        self.assertEqual(self.source.split(marker, 1)[1].strip(), "")


if __name__ == "__main__":
    unittest.main()
