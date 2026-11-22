"""Offline unit tests for VBox guest preflight evidence normalization.

Run on a Windows host. No real VirtualBox, Linux Mint VM or compiled Qt is
started or claimed. All evidence here is synthetic and in-memory.
"""
import copy
import json
from unittest import mock
import unittest

from canopy_features.mint import vbox_guest_readiness as readiness
from tools import mint_guest_preflight as guest


def sample_evidence(**overrides):
    release = {"ID": "linuxmint", "VERSION_ID": "22.3", "PRETTY_NAME": "Linux Mint 22.3"}
    env = {
        "DISPLAY": ":0",
        "XDG_CURRENT_DESKTOP": "X-Cinnamon",
        "XDG_SESSION_TYPE": "x11",
    }
    available = {name: True for name in guest.NEEDED}
    evidence = {
        "release": release,
        "env": env,
        "available": available,
        "qt_version": "6.4.2",
        "vm_name": "mint-guest-r2",
        "power_state": "running",
        "vboxmanage_available": True,
    }
    evidence.update(overrides)
    return evidence


class VBoxGuestReadinessTests(unittest.TestCase):
    def setUp(self):
        self.evidence = sample_evidence()

    def report(self, **overrides):
        return readiness.normalize(sample_evidence(**overrides))

    def test_reuses_existing_preflight_evaluator(self):
        report = self.report()
        expected = guest.assess(
            self.evidence["release"], self.evidence["env"],
            self.evidence["available"], self.evidence["qt_version"],
        )
        self.assertEqual(report["preflight"], expected)
        self.assertEqual(report["preflight"]["status"], "READY_FOR_TESTS")

    def test_never_claims_actual_run(self):
        report = self.report()
        self.assertEqual(report["status"], "NORMALIZED_NOT_RUN")
        self.assertIs(report["actual_run"], False)
        self.assertIs(report["vboxmanage_invoked"], False)
        self.assertIs(report["vm_started"], False)
        self.assertIs(report["linux_mint_execution_independently_proven"], False)
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
        self.assertEqual(report["runtime_functional_test"], "NOT_RUN")
        self.assertEqual(report["visual_acceptance"], "NOT_RUN")

    def test_powered_off_vm_is_blocked(self):
        report = self.report(power_state="poweroff")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIs(report["guest_evidence_attributable_to_live_vm"], False)
        self.assertIs(report["actual_run"], False)
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
        self.assertIn("power_state=poweroff", " ".join(report["blockers"]))
        # A READY preflight claim is preserved but never promoted to a run.
        self.assertEqual(report["preflight"]["status"], "READY_FOR_TESTS")

    def test_absent_vboxmanage_is_blocked(self):
        report = self.report(vboxmanage_available=False)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIs(report["guest_evidence_attributable_to_live_vm"], False)
        self.assertIs(report["vboxmanage_invoked"], False)
        self.assertIn("VBoxManage unavailable", " ".join(report["blockers"]))
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")

    def test_non_running_states_are_not_attributed_to_live_vm(self):
        for state in ("saved", "paused", "unknown"):
            with self.subTest(power_state=state):
                report = self.report(power_state=state)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertIs(report["guest_evidence_attributable_to_live_vm"], False)

    def test_no_live_probe_performed(self):
        with mock.patch.object(guest, "collect",
                               side_effect=AssertionError("host probe called")):
            report = readiness.normalize(copy.deepcopy(self.evidence))
        self.assertEqual(report["status"], "NORMALIZED_NOT_RUN")

    def test_non_mint_preflight_blocked_without_run_claim(self):
        report = self.report(release={"ID": "ubuntu", "VERSION_ID": "24.04"})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["preflight"]["mint_identified"])
        self.assertTrue(any("not verified as Linux Mint" in item
                            for item in report["blockers"]))
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")

    def test_private_env_values_not_leaked(self):
        evidence = sample_evidence()
        evidence["env"]["SSH_AUTH_SOCK"] = "/home/secret/socket"
        evidence["env"]["CANOPY_TOKEN"] = "very-secret-token"
        report = readiness.normalize(evidence)
        serialized = json.dumps(report)
        self.assertNotIn("/home/secret/socket", serialized)
        self.assertNotIn("very-secret-token", serialized)
        self.assertNotIn("SSH_AUTH_SOCK", serialized)

    def test_rejects_unknown_or_extra_evidence_keys(self):
        incomplete = sample_evidence()
        incomplete.pop("vm_name")
        with self.assertRaises(readiness.EvidenceError):
            readiness.normalize(incomplete)
        extra = sample_evidence()
        extra["unexpected"] = "x"
        with self.assertRaises(readiness.EvidenceError):
            readiness.normalize(extra)
        with self.assertRaises(readiness.EvidenceError):
            readiness.normalize([])

    def test_rejects_invalid_power_state_and_vboxmanage_flag(self):
        with self.assertRaises(readiness.EvidenceError):
            self.report(power_state="maybe")
        with self.assertRaises(readiness.EvidenceError):
            self.report(power_state=None)
        with self.assertRaises(readiness.EvidenceError):
            self.report(vboxmanage_available="yes")

    def test_bounds_text_maps_and_qt_version(self):
        with self.assertRaises(readiness.EvidenceError):
            self.report(vm_name="x" * (readiness.MAX_TEXT + 1))
        with self.assertRaises(readiness.EvidenceError):
            self.report(vm_name="bad\nname")
        with self.assertRaises(readiness.EvidenceError):
            self.report(env={"A": "y" * (readiness.MAX_MAP_TEXT + 1)})
        with self.assertRaises(readiness.EvidenceError):
            self.report(qt_version="6.4.2;rm -rf")
        with self.assertRaises(readiness.EvidenceError):
            self.report(available={name: True for name in range(readiness.MAX_MAP_ENTRIES + 1)})

    def test_absent_qt_is_blocked_not_a_run(self):
        report = self.report(qt_version=None)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIs(report["actual_run"], False)
        self.assertIn("Qt6Core", " ".join(report["blockers"]))


if __name__ == "__main__":
    unittest.main()
