"""Regression: a READY_FOR_TESTS status with non-empty blockers is contradictory.

The preflight producer sets ``status = READY_FOR_TESTS`` only when its blocker
list is empty.  A captured report that claims READY while still listing a
blocker is internally inconsistent: normalizing it previously surfaced the
READY field verbatim and let ``build_normalized_evidence`` emit a false
``READY_FOR_TESTS_EVIDENCE_ONLY`` guest-ready claim.  These tests pin the
fail-closed contract (``EvidenceError``) at every public entry point and keep
the two legal READY/BLOCKED combinations as controls.

Synthetic captured data only: no VM, no VBoxManage execution, no Qt run and no
Linux Mint acceptance is claimed or performed.
"""
import unittest

from canopy_features.mint.vbox_guest_readiness import (
    EvidenceError, MAX_BLOCKERS, build_normalized_evidence, load_preflight,
    normalize_preflight,
)

_READY_WITH_BLOCKERS = {
    "schema_version": 1,
    "probe_only": True,
    "status": "READY_FOR_TESTS",
    "mint_identified": True,
    "version_id": "22.3",
    "cinnamon_identified": True,
    "graphical_display_present": True,
    "session_type": "x11",
    "qt6_core_version": "6.4.2",
    "commands_present": {"cmake": True, "pkg-config": True,
                         "ninja": True, "xvfb-run": True},
    # The contradiction: READY status paired with a concrete hard blocker.
    "blockers": ["required build tool not found: ninja"],
}

_RUNNING_VMINFO = 'name="mint-guest"\nVMState="running"\n'


class ReadyBlockedContradictionTests(unittest.TestCase):
    def assert_domain_error(self, fn):
        """The documented domain error, never a false READY record."""
        with self.assertRaises(EvidenceError):
            fn()

    def test_normalize_preflight_refuses_ready_with_blockers(self):
        self.assert_domain_error(
            lambda: normalize_preflight(_READY_WITH_BLOCKERS))

    def test_build_evidence_refuses_ready_with_blockers(self):
        self.assert_domain_error(
            lambda: build_normalized_evidence(
                _READY_WITH_BLOCKERS, vminfo_text=_RUNNING_VMINFO))

    def test_load_then_build_refuses_ready_with_blockers(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "contradictory-preflight.json"
            path.write_text(json.dumps(_READY_WITH_BLOCKERS), encoding="utf-8")
            loaded = load_preflight(path)

        def chain():
            record = build_normalized_evidence(
                loaded, vminfo_text=_RUNNING_VMINFO)
            # No contradictory record may escape as a ready claim.
            self.assertNotEqual(
                record.get("readiness"), "READY_FOR_TESTS_EVIDENCE_ONLY")

        self.assert_domain_error(chain)

    def test_ready_with_empty_blockers_still_allowed(self):
        clean = dict(_READY_WITH_BLOCKERS, blockers=[])
        guest = normalize_preflight(clean)
        record = build_normalized_evidence(clean, vminfo_text=_RUNNING_VMINFO)
        self.assertEqual(guest["status"], "READY_FOR_TESTS")
        self.assertEqual(record["readiness"], "READY_FOR_TESTS_EVIDENCE_ONLY")

    def test_blocked_with_blockers_still_allowed(self):
        blocked = dict(_READY_WITH_BLOCKERS, status="BLOCKED")
        record = build_normalized_evidence(
            blocked, vminfo_text=_RUNNING_VMINFO)
        self.assertEqual(record["readiness"], "BLOCKED_EVIDENCE")

    def test_blockers_over_bound_still_rejected(self):
        oversized = dict(_READY_WITH_BLOCKERS, blockers=["x"] * (MAX_BLOCKERS + 1))
        self.assert_domain_error(lambda: normalize_preflight(oversized))


if __name__ == "__main__":
    unittest.main()
