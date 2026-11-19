from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] /
          "scripts/Install-CanopyMintOS.ps1").read_text(encoding="utf-8")


class UnattendedInstallContract(unittest.TestCase):
    def test_opt_in_and_dry_run(self):
        for value in ("[switch]$Install", "'--dry-run'", "if (-not $Install)",
                      "Get-FileHash", "VMState=", "Canopy-Test-Mint",
                      "--user-password-file=", "--no-install-additions"):
            self.assertIn(value, SOURCE)

    def test_no_host_destruction_or_password_printing(self):
        for forbidden in ("Remove-VM", "unregistervm", "delete", "Format-Volume",
                          "Invoke-Expression", "Set-ExecutionPolicy", "Write-Output $secret"):
            self.assertNotIn(forbidden, SOURCE)


if __name__ == "__main__":
    unittest.main()
