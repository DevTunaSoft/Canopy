"""Regression tests for contradictory portal capability records in the boot snapshot.

A ``PortalCapabilityReport`` carries both per-capability ``capabilities`` and
summary sets (usable/denied/missing/unknown_permission). The boot snapshot must
not accept a bounded-but-contradictory pair: a summary that claims a granted
portal while the detail records a denial is a false boot-ready claim.
"""

import unittest
from dataclasses import replace

from canopy_features.reliability import startup_checkpoints as cp
from canopy_features.windows import boot_backend_snapshot as module
from canopy_features.windows import wayland_portal_capabilities as portal
from canopy_features.windows import window_state_capabilities as wsc


def _startup():
    return cp.RecoveryDecision(cp.READY, ("shell",), (), None, "durable")


def _neg():
    return wsc.negotiate("x11", [wsc.WindowStateFeature.MINIMIZE])


def _granted():
    return portal.describe("wayland", ("remote_desktop", "screen_cast"),
                           {"remote_desktop": "granted",
                            "screen_cast": "granted"})


def _denied():
    return portal.describe("wayland", ("remote_desktop", "screen_cast"),
                           {"remote_desktop": "denied",
                            "screen_cast": "denied"})


def _missing():
    return portal.describe("wayland", (), {})


class BootBackendContradictoryPortalTests(unittest.TestCase):
    def test_granted_summary_with_denied_details_is_rejected(self):
        report = replace(_granted(), capabilities=_denied().capabilities)
        with self.assertRaises(module.SnapshotError):
            module.compose(_startup(), report, _neg())

    def test_denied_hidden_behind_granted_details_is_rejected(self):
        report = replace(_denied(),
                         denied=frozenset(),
                         usable=_granted().usable)
        with self.assertRaises(module.SnapshotError):
            module.compose(_startup(), report, _neg())

    def test_granted_summary_with_missing_details_is_rejected(self):
        report = replace(_granted(), capabilities=_missing().capabilities)
        with self.assertRaises(module.SnapshotError):
            module.compose(_startup(), report, _neg())

    def test_duplicate_capability_entries_are_rejected(self):
        granted = _granted()
        report = replace(granted, capabilities=granted.capabilities[:1]
                         + granted.capabilities[:1])
        with self.assertRaises(module.SnapshotError):
            module.compose(_startup(), report, _neg())

    def test_capability_usable_flag_must_match_its_status(self):
        granted = _granted()
        first, second = granted.capabilities
        forged = replace(first, usable=False)
        report = replace(granted, capabilities=(forged, second))
        with self.assertRaises(module.SnapshotError):
            module.compose(_startup(), report, _neg())

    def test_genuine_reports_still_compose(self):
        self.assertEqual(module.compose(_startup(), _granted(), _neg()).status,
                         module.STATUS_OK)
        self.assertEqual(module.compose(_startup(), _denied(), _neg()).status,
                         module.STATUS_BLOCKED)
        self.assertEqual(module.compose(_startup(), _missing(), _neg()).status,
                         module.STATUS_ATTENTION)


if __name__ == "__main__":
    unittest.main()
