"""Static safeguards for Windows VM hardware creation script."""
from pathlib import Path
import unittest
SOURCE=(Path(__file__).resolve().parents[1]/"scripts/New-CanopyMintVM.ps1").read_text(encoding="utf-8")
class VmCreateContract(unittest.TestCase):
    def test_explicit_creation_guard(self):
        self.assertIn("if (-not $Create)",SOURCE)
        self.assertIn("Get-FileHash",SOURCE)
        self.assertIn("already exists",SOURCE)
        self.assertIn("Canopy-Test-Mint",SOURCE)
    def test_isolated_nat_and_guest_separation(self):
        for required in ("127.0.0.1,2222,,22","--clipboard-mode", "'disabled'",
                         "--draganddrop", "'nat'","'40960'"):
            self.assertIn(required,SOURCE)
        for forbidden in ("Remove-VM","Format-Volume","Remove-Item -Recurse",
                          "Set-ExecutionPolicy", "Invoke-Expression"):
            self.assertNotIn(forbidden,SOURCE)
if __name__=="__main__":
    unittest.main()
