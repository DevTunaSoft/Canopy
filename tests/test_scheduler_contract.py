"""Ensure unattended Windows scheduling requires consent and least privileges."""
from pathlib import Path
import unittest
FILE = Path(__file__).resolve().parents[1]/"scripts/Enable-CanopyTestLabSchedule.ps1"
class HostScheduleContractTests(unittest.TestCase):
    def test_only_dedicated_low_privilege_task(self):
        source=FILE.read_text(encoding="utf-8")
        for required in ("$Enable", "$Disable", "$SelfTest",
                         "CanopyTestLab-ApprovedTests","-LogonType Interactive",
                         "-RunLevel Limited","-MultipleInstances IgnoreNew",
                         "-ExecutionTimeLimit", "Unregister-ScheduledTask"):
            self.assertIn(required,source)
        for forbidden in ("-RunLevel Highest", "-LogonType Password",
                          "'SYSTEM'", "NT AUTHORITY\\SYSTEM",
                          "-ExecutionPolicy Bypass", "Invoke-Expression"):
            self.assertNotIn(forbidden,source)
    def test_30_minute_schedule_and_no_force(self):
        source=FILE.read_text(encoding="utf-8")
        self.assertIn("New-TimeSpan -Minutes 30",source)
        self.assertIn("refusing to overwrite",source)
        self.assertIn("No scheduled task changes",source)
if __name__=="__main__":
    unittest.main()
