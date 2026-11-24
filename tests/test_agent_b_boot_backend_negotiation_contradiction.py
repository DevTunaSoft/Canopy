"""Regression tests for contradictory negotiation records in the boot snapshot.

A ``Negotiation`` carries both a status (SUPPORTED/PARTIAL/UNSUPPORTED) and a
``granted`` feature set; its public ``supported`` flag is derived from the
granted set. The boot snapshot must not accept a bounded-but-contradictory
pair: status SUPPORTED with no granted features composes as a false boot-ready
claim, while UNSUPPORTED with granted features is an equally false block.
"""

import unittest

from canopy_features.reliability import startup_checkpoints as cp
from canopy_features.windows import boot_backend_snapshot as module
from canopy_features.windows import wayland_portal_capabilities as portal
from canopy_features.windows import window_state_capabilities as wsc


def _startup():
    return cp.RecoveryDecision(cp.READY, ("shell",), (), None, "durable")


def _portal():
    return portal.describe("wayland", ("remote_desktop", "screen_cast"),
                           {"remote_desktop": "granted",
                            "screen_cast": "granted"})


def _compose(negotiation):
    return module.compose(_startup(), _portal(), negotiation)


class BootBackendNegotiationContradictionTests(unittest.TestCase):
    def test_supported_status_with_empty_granted_is_rejected(self):
        negotiation = wsc.Negotiation("x11", "SUPPORTED", frozenset())
        self.assertFalse(negotiation.supported)
        with self.assertRaises(module.SnapshotError):
            _compose(negotiation)

    def test_unsupported_status_with_granted_is_rejected(self):
        negotiation = wsc.Negotiation(
            "x11", "UNSUPPORTED", frozenset({wsc.WindowStateFeature.MINIMIZE}))
        self.assertTrue(negotiation.supported)
        with self.assertRaises(module.SnapshotError):
            _compose(negotiation)

    def test_partial_with_granted_still_composes_attention(self):
        negotiation = wsc.Negotiation(
            "x11", "PARTIAL", frozenset({wsc.WindowStateFeature.MINIMIZE}))
        record = _compose(negotiation)
        self.assertEqual(record.status, module.STATUS_ATTENTION)
        self.assertTrue(record.negotiation.supported)
        self.assertEqual(record.negotiation.granted, ("minimize",))

    def test_genuine_negotiations_still_compose(self):
        supported = wsc.negotiate("x11", [wsc.WindowStateFeature.MINIMIZE])
        self.assertEqual(_compose(supported).status, module.STATUS_OK)
        unsupported = wsc.Negotiation("x11", "UNSUPPORTED", frozenset())
        self.assertEqual(_compose(unsupported).status, module.STATUS_BLOCKED)


if __name__ == "__main__":
    unittest.main()
