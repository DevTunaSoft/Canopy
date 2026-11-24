"""RecoveryDecision subclass override must not forge boot-ready flags."""
import unittest

from canopy_features.reliability import startup_checkpoints as cp
from canopy_features.windows import boot_backend_snapshot as m
from canopy_features.windows import wayland_portal_capabilities as portal
from canopy_features.windows import window_state_capabilities as wsc


class ForgedRecovery(cp.RecoveryDecision):
    """Subclass whose properties contradict its durable action/unwind fields."""

    @property
    def safe_to_start(self):
        return True

    @property
    def needs_rollback(self):
        return False


def _portal():
    return portal.describe(
        "wayland", ("remote_desktop", "screen_cast"),
        {"remote_desktop": "granted", "screen_cast": "granted"})


def _neg():
    return wsc.negotiate("x11", [wsc.WindowStateFeature.MINIMIZE])


class BootBackendRecoveryOverrideTests(unittest.TestCase):
    def test_forged_recovery_flags_fail_closed(self):
        decision = ForgedRecovery(cp.ROLLBACK, ("shell",), ("unwind",),
                                  None, "durable")
        with self.assertRaises(m.SnapshotError):
            m.compose(decision, _portal(), _neg())

    def test_genuine_rollback_still_composes_to_attention(self):
        decision = cp.RecoveryDecision(cp.ROLLBACK, ("shell",), ("unwind",),
                                       None, "durable")
        result = m.compose(decision, _portal(), _neg())
        self.assertEqual(result.status, m.STATUS_BLOCKED)
        self.assertTrue(result.startup.needs_rollback)


if __name__ == "__main__":
    unittest.main()
