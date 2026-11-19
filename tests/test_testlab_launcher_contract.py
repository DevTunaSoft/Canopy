from pathlib import Path
import unittest

SOURCE=(Path(__file__).resolve().parents[1]/"scripts/Start-CanopyTestLab.ps1").read_text(encoding="utf-8")


class TestLabLauncherContract(unittest.TestCase):
    def test_explicit_consent_and_verified_iso(self):
        for token in ('[switch]$Provision','[switch]$ConfigureUnattended',
                      "IsoSha256", "Test-CanopyHost.ps1", "New-CanopyMintVM.ps1",
                      "Install-CanopyMintOS.ps1", "if (-not $Provision)"):
            self.assertIn(token,SOURCE)

    def test_no_unapproved_host_actions(self):
        for token in ('Invoke-Expression','Set-ExecutionPolicy','unregistervm',
                      'Remove-VM','Start-Process','Invoke-WebRequest'):
            self.assertNotIn(token,SOURCE)


if __name__=="__main__":
    unittest.main()
