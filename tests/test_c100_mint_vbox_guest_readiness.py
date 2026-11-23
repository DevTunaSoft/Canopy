"""Offline tests for VirtualBox guest preflight evidence normalization.

These tests consume synthetic captured data only. They do not start a VM,
run VBoxManage, compile Qt, or test a real Linux Mint guest.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from canopy_features.mint.vbox_guest_readiness import (
    EvidenceError, build_normalized_evidence, load_preflight,
    locate_vboxmanage, normalize_preflight, normalize_vm, parse_vminfo,
)

NOT_RUN_FIELDS = (
    "mint_guest_acceptance", "runtime_functional_test",
    "visual_acceptance", "owner_visual_approval",
)


class VBoxGuestReadinessTests(unittest.TestCase):
    def setUp(self):
        self.preflight = {
            "schema_version": 1,
            "probe_only": True,
            "status": "READY_FOR_TESTS",
            "mint_identified": True,
            "version_id": "22.3",
            "cinnamon_identified": True,
            "graphical_display_present": True,
            "session_type": "x11",
            "qt6_core_version": "6.4.2",
            "commands_present": {
                "cmake": True, "pkg-config": True,
                "ninja": True, "xvfb-run": True,
            },
            "blockers": [],
            # Hostile extras must never survive normalization.
            "mint_guest_acceptance": "PASS",
            "runtime_functional_test": "PASS",
            "visual_acceptance": "PASS",
        }
        self.vminfo_running = (
            'name="mint-guest"\n'
            'VMState="running"\n'
            'GuestAdditionsVersion="7.0.0"\n'
            'MACAddress="AA:BB:CC:DD:EE:FF"\n'
        )
        self.vminfo_poweroff = 'name="mint-guest"\nVMState="poweroff"\n'

    def build(self, **kwargs):
        return build_normalized_evidence(self.preflight, **kwargs)

    def assert_no_run_claimed(self, report):
        self.assertIs(report["actual_run_performed"], False)
        self.assertEqual(report["run_claim"], "NONE")
        self.assertIs(
            report["linux_mint_execution_independently_proven"], False
        )
        for field in NOT_RUN_FIELDS:
            self.assertEqual(report["acceptance"][field], "NOT_RUN")

    def test_running_vm_snapshot_never_claims_run_or_acceptance(self):
        report = self.build(vminfo_text=self.vminfo_running,
                            vboxmanage_path="/usr/bin/VBoxManage")
        self.assert_no_run_claimed(report)
        self.assertEqual(report["readiness"], "READY_FOR_TESTS_EVIDENCE_ONLY")
        self.assertIs(report["vm"]["vboxmanage_present"], True)
        self.assertIs(report["vm"]["vm_powered_off"], False)
        self.assertEqual(report["vm"]["vm_state_at_capture"], "running")

    def test_powered_off_vm_is_explicit(self):
        report = self.build(vminfo_text=self.vminfo_poweroff)
        vm = report["vm"]
        self.assertIs(vm["vm_powered_off"], True)
        self.assertEqual(vm["vm_state_at_capture"], "poweroff")
        self.assertTrue(any("poweroff" in note for note in vm["notes"]))
        self.assert_no_run_claimed(report)
        self.assertIs(vm["vminfo_available"], True)

    def test_absent_vboxmanage_is_explicit(self):
        report = self.build(vminfo_text=None, vboxmanage_path=None)
        vm = report["vm"]
        self.assertIs(vm["vboxmanage_present"], False)
        self.assertIs(vm["vminfo_available"], False)
        self.assertIsNone(vm["vm_state_at_capture"])
        self.assertIsNone(vm["vm_powered_off"])
        self.assertTrue(any("VBoxManage unavailable" in n for n in vm["notes"]))
        self.assert_no_run_claimed(report)

    def test_normalize_vm_absent_without_preflight(self):
        vm = normalize_vm()
        self.assertIs(vm["vboxmanage_present"], False)
        self.assertIsNone(vm["vm_name"])
        self.assertEqual(vm["notes"],
                         ["VBoxManage unavailable; no VM state evidence supplied"])

    def test_vminfo_allowlist_drops_host_private_fields(self):
        report = self.build(vminfo_text=self.vminfo_running)
        serialized = json.dumps(report)
        self.assertNotIn("MACAddress", serialized)
        self.assertNotIn("AA:BB:CC:DD:EE:FF", serialized)
        self.assertNotIn("GuestAdditionsVersion", serialized)
        self.assertNotIn("7.0.0", serialized)
        self.assertEqual(report["vm"]["vm_name"], "mint-guest")

    def test_parse_vminfo_bounds_and_control_chars(self):
        self.assertEqual(parse_vminfo(None), {})
        self.assertEqual(parse_vminfo(""), {})
        oversized = "name=\"" + "x" * 200_000 + "\"\n"
        with self.assertRaises(EvidenceError):
            parse_vminfo(oversized)
        parsed = parse_vminfo(
            'VMState="poweroff"\n'
            'name="bad\x00value"\n'
            'OtherKey="ignored"\n'
        )
        self.assertEqual(parsed, {"VMState": "poweroff"})

    def test_blocked_preflight_is_not_presented_as_run(self):
        blocked = dict(self.preflight, status="BLOCKED",
                       blockers=["required build tool not found: ninja"])
        report = build_normalized_evidence(
            blocked, vminfo_text=self.vminfo_poweroff,
        )
        self.assertEqual(report["readiness"], "BLOCKED_EVIDENCE")
        self.assertEqual(report["guest"]["status"], "BLOCKED")
        self.assert_no_run_claimed(report)

    def test_hostile_preflight_acceptance_fields_are_dropped(self):
        report = self.build(vminfo_text=self.vminfo_running)
        self.assert_no_run_claimed(report)
        self.assertNotIn("mint_guest_acceptance", report["guest"])

    def test_invalid_preflight_rejected(self):
        bad_cases = [
            None,
            dict(self.preflight, probe_only=False),
            dict(self.preflight, schema_version=99),
            dict(self.preflight, status="PASS"),
            dict(self.preflight, mint_identified="yes"),
            dict(self.preflight, blockers=["x"] * 25),
            dict(self.preflight, commands_present=["cmake"]),
            dict(self.preflight, session_type="tty"),
        ]
        for case in bad_cases:
            with self.subTest(case=type(case).__name__):
                with self.assertRaises(EvidenceError):
                    normalize_preflight(case)

    def test_normalization_does_not_mutate_input(self):
        before = copy.deepcopy(self.preflight)
        self.build(vminfo_text=self.vminfo_running)
        self.assertEqual(self.preflight, before)

    def test_output_is_bounded_deterministic_json(self):
        first = self.build(vminfo_text=self.vminfo_poweroff)
        second = self.build(vminfo_text=self.vminfo_poweroff)
        self.assertEqual(first, second)
        encoded = json.dumps(first, sort_keys=True)
        self.assertLess(len(encoded), 16_000)

    def test_locate_vboxmanage_injected_absent_and_present(self):
        self.assertIsNone(locate_vboxmanage(which=lambda name: None))
        self.assertEqual(
            locate_vboxmanage(which=lambda name: "/usr/bin/" + name
                              if name == "VBoxManage" else None),
            "/usr/bin/VBoxManage",
        )

    def test_locate_vboxmanage_host_check_is_read_only(self):
        # PATH lookup only; safe on Windows host and on a Linux Mint guest.
        found = locate_vboxmanage()
        self.assertTrue(found is None or isinstance(found, str))

    def test_load_preflight_from_saved_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mint-guest-preflight.json"
            path.write_text(json.dumps(self.preflight), encoding="utf-8")
            loaded = load_preflight(path)
            self.assertEqual(loaded["status"], "READY_FOR_TESTS")
            report = build_normalized_evidence(
                loaded, vminfo_text=self.vminfo_poweroff,
            )
            self.assert_no_run_claimed(report)

    def test_load_preflight_rejects_nonfinite_number(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text('{"x": NaN}', encoding="utf-8")
            with self.assertRaises(EvidenceError):
                load_preflight(path)


if __name__ == "__main__":
    unittest.main()
