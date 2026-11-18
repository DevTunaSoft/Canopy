"""Verify bootstrap doesn't silently install, download, or expose host services."""
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "scripts/Install-Canopy-TestLab.ps1"


class BootstrapContractTests(unittest.TestCase):
    def test_declared_plan_and_non_destructive_behavior(self):
        source = PATH.read_text(encoding="utf-8")
        for marker in ("New-CanopyBootstrapPlan", "provisioning_status = 'NOT_RUN'",
                       "ConvertTo-Json", "Test-CanopyHost.ps1", "bootstrap-plan.json"):
            self.assertIn(marker, source)
        for forbidden in ("Invoke-WebRequest", "Start-Process", "Register-ScheduledTask",
                          "New-NetFirewallRule", "VBoxManage.exe createvm",
                          "Set-ExecutionPolicy", "iex "):
            self.assertNotIn(forbidden, source)

    def test_local_only_destination(self):
        source = PATH.read_text(encoding="utf-8")
        self.assertIn("Join-Path $env:LOCALAPPDATA 'CanopyTestLab'", source)
        self.assertIn("host-preflight.json", source)


if __name__ == "__main__":
    unittest.main()
