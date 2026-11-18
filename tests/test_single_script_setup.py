from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1]/"Canopy-Setup.ps1").read_text(encoding="utf-8")


class SingleScriptSetupContract(unittest.TestCase):
    def test_orchestration(self):
        for token in ("Start-CanopyTestLab.ps1", "clone", "pull '--ff-only'",
                      "Canopy-Test-Mint", "Get-Command git.exe",
                      "IsoSha256", "[string]$IsoUrl", "Get-VerifiedMintIso", "Invoke-WebRequest", "Get-FileHash", "[switch]$StartVM", "[switch]$SelfTest"):
            self.assertIn(token, SOURCE)

    def test_no_untrusted_execution(self):
        for token in ("Invoke-Expression", "iex ", "ExecutionPolicy Bypass",
                      "unregistervm", "Remove-Item -Recurse", "curl |"):
            self.assertNotIn(token, SOURCE)


if __name__ == "__main__":
    unittest.main()
