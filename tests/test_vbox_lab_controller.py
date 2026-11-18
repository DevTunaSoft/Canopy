import subprocess
import unittest
from scripts.vbox_lab_controller import operate, inspect_vm, machine_values


UUID = "11111111-2222-3333-4444-555555555555"


def fake(state="poweroff", *, snapshots=True, start_succeeds=True):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv[1:])
        args = argv[1:]
        if args[0] == "showvminfo":
            current = "running" if any(c[0] == "startvm" for c in calls) and start_succeeds else state
            return subprocess.CompletedProcess(argv, 0,
                'name="Canopy-Test-Mint"\nUUID="' + UUID + '"\nVMState="' + current + '"\n', "")
        if args[0] == "snapshot" and args[2] == "showvminfo" and not snapshots:
            return subprocess.CompletedProcess(argv, 1, "", "missing snapshot")
        return subprocess.CompletedProcess(argv, 0, "", "")
    return run, calls


class VBoxControllerTests(unittest.TestCase):
    def test_name_and_state_parsing(self):
        self.assertEqual(machine_values('name="Canopy-Test-Mint"\nVMState="poweroff"')['name'],
                         "Canopy-Test-Mint")
        runner, _ = fake()
        self.assertEqual(inspect_vm("vbox", runner=runner)["state"], "poweroff")

    def test_status_is_non_destructive(self):
        runner, calls = fake()
        outcome = operate("vbox", "status", runner=runner)
        self.assertEqual(outcome["status"], "PASS")
        self.assertEqual(len(calls), 1)

    def test_start_only_from_poweroff(self):
        runner, calls = fake()
        self.assertEqual(operate("vbox", "start", runner=runner)["vm"]["state"], "running")
        self.assertTrue(any(c[0] == "startvm" for c in calls))
        runner, calls = fake(state="running")
        with self.assertRaises(ValueError):
            operate("vbox", "start", runner=runner)
        self.assertEqual(len(calls), 1)

    def test_reset_requires_explicit_authorization_and_known_snapshot(self):
        runner, calls = fake()
        with self.assertRaises(PermissionError):
            operate("vbox", "reset", runner=runner)
        self.assertEqual(len(calls), 1)
        runner, calls = fake(snapshots=False)
        with self.assertRaises(RuntimeError):
            operate("vbox", "reset", runner=runner, allow_reset=True)
        self.assertFalse(any(c[:3] == ["snapshot", "Canopy-Test-Mint", "restore"] for c in calls))

    def test_reset_only_when_off_and_explicit(self):
        runner, calls = fake()
        outcome = operate("vbox", "reset", runner=runner, allow_reset=True)
        self.assertEqual(outcome["snapshot"], "Canopy-Clean")
        self.assertTrue(any(c[:3] == ["snapshot", "Canopy-Test-Mint", "restore"] for c in calls))
        runner, calls = fake(state="running")
        with self.assertRaises(ValueError):
            operate("vbox", "reset", runner=runner, allow_reset=True)
        self.assertEqual(len(calls), 1)

    def test_reject_unexpected_identity(self):
        def wrong(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0,
                'name="Someone Else"\nUUID="' + UUID + '"\nVMState="poweroff"\n', "")
        with self.assertRaises(ValueError):
            operate("vbox", "status", runner=wrong)

    def test_failed_start_does_not_claim_success(self):
        runner, _ = fake(start_succeeds=False)
        with self.assertRaises(RuntimeError):
            operate("vbox", "start", runner=runner)


if __name__ == "__main__":
    unittest.main()
