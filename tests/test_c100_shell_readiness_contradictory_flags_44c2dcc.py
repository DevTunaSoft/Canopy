"""Contradictory ready/blocked flags in shell readiness composition.

Audit slice at tip 44c2dcc. A caller-supplied reliability record is bounded
but can claim ``status="OK"`` while its durable startup detail says the
opposite: an unsafe startup, a rollback flag, unwind steps, a blocked action,
or a wrong-type (int) ready flag. The composer must fail closed with
``ReadinessError`` instead of copying a false ready token into the snapshot.

Resource note: all evidence here is SYNTHETIC (pure in-memory composition).
No real startup, delivery channel, shell, Qt/Mint session or screen-reader
path was exercised; those remain NOT_RUN.
"""
import unittest

from canopy_features.host.shell_readiness_snapshot import ReadinessError, compose
from canopy_features.performance.frame_pacing import parse_frame_times
from canopy_features.performance.performance_snapshot import compose_snapshot
from canopy_features.security.security_decision_snapshot import (
    SecurityDecisionSnapshot,
)


def security():
    return SecurityDecisionSnapshot(
        schema=1, uri_status="PERMITTED", privilege_status="ALLOWED",
        privilege_reason="allowed", metadata_status="SAFE",
        metadata_capability_count=2,
    ).as_dict()


def reliability(status="OK", **startup_overrides):
    startup = {
        "action": "READY", "safe_to_start": True, "needs_rollback": False,
        "completed_count": 3, "unwind_count": 0, "reason": "SECRET_STARTUP_MARKER",
    }
    startup.update(startup_overrides)
    return {
        "schema": 1, "status": status, "acceptance": "NOT_ESTABLISHED",
        "startup": startup,
        "delivery": {"sent": 2, "received": 2, "delivered": 2, "duplicates": 0,
                     "reordered": 0, "gaps": 0, "missed": 0, "dropped": 0,
                     "rejected": 0, "notice_count": 0, "last_policy": "queue"},
        "switcher": {"active": True, "current": "w1", "selected": "w1",
                     "window_count": 1, "order": ("w1",)},
    }


def performance():
    return compose_snapshot(
        frame_pacing=parse_frame_times([16.7], refresh_hz=60), pss_kib=150_000,
    ).as_dict()


def installer():
    return {
        "status": "PLAN_SNAPSHOT", "schema": 1, "icon_status": "AVAILABLE",
        "xdg_status": "WITHIN_HOME", "ownership_status": "VALID",
        "ownership_file_count": 1, "session_status": "VALID",
        "filesystem_verified": False, "binary_verified": False,
        "uninstall_executed": False, "session_registered": False,
        "package_installed": False, "release_approved": False,
        "linux_mint_acceptance_proven": False, "owner_visual_approval": False,
    }


def window(status="OK"):
    return {
        "schema": 1, "status": status, "acceptance": "NOT_ESTABLISHED",
        "switcher": {"active": True, "current": "w1", "selected": "w1",
                     "window_count": 1, "order": ("w1",)},
        "workspace": {"workspace_count": 1, "identifiers": ("ws1",),
                      "problem_count": 0, "problem_reasons": ()},
        "portal": {"session_type": "x11", "wayland": False,
                   "window_enumeration": "available", "capability_count": 0,
                   "usable": True, "denied": (), "missing": (),
                   "unknown_permission": ()},
        "negotiation": {"backend": "x11", "status": "SUPPORTED",
                        "granted": (), "supported": ()},
    }


def record(**overrides):
    base = {
        "schema": 1, "security": security(), "reliability": reliability(),
        "performance": performance(), "installer": installer(),
        "window": window(),
    }
    base.update(overrides)
    return base


class ContradictoryReadyFlagTests(unittest.TestCase):
    """A bounded OK summary with blocked detail is a false ready claim."""

    def _reject(self, **startup_overrides):
        with self.assertRaises(ReadinessError):
            compose(record(reliability=reliability("OK", **startup_overrides)))

    def test_ok_status_cannot_hide_unsafe_startup(self):
        self._reject(safe_to_start=False)

    def test_ok_status_cannot_hide_rollback_flag(self):
        self._reject(needs_rollback=True, unwind_count=1)

    def test_ok_status_cannot_hide_unwind_steps(self):
        self._reject(needs_rollback=False, unwind_count=2)

    def test_ok_status_cannot_hide_blocked_action(self):
        self._reject(action="ROLLBACK")

    def test_ok_status_cannot_hide_fail_closed_action(self):
        self._reject(action="FAIL_CLOSED")

    def test_ok_status_cannot_hide_wrong_type_ready_flag(self):
        # Bounded int, not a bool: accepted by generic leaf bounding on base.
        self._reject(safe_to_start=1)

    def test_ok_status_cannot_hide_wrong_type_rollback_flag(self):
        self._reject(needs_rollback=0, unwind_count=1)

    def test_ok_status_cannot_hide_wrong_type_action_token(self):
        # Unhashable list would raise a raw TypeError in a membership test.
        self._reject(action=[])

    def test_ok_status_cannot_hide_wrong_type_unwind_count(self):
        self._reject(unwind_count=True, needs_rollback=False)


class CoherentRecordTests(unittest.TestCase):
    """The guard must not weaken coherent OK / explicit BLOCKED records."""

    def test_coherent_ok_still_composes(self):
        out = compose(record()).as_dict()
        self.assertEqual(out["component_tokens"][1], "OK")
        self.assertEqual(out["component_count"], 5)

    def test_explicit_blocked_status_still_preserved(self):
        rec = record(reliability=reliability(
            "BLOCKED", action="ROLLBACK", safe_to_start=False,
            needs_rollback=True, unwind_count=1))
        out = compose(rec).as_dict()
        self.assertEqual(out["component_tokens"][1], "BLOCKED")
        self.assertIs(out["shell_running"], False)

    def test_attention_status_still_preserved(self):
        out = compose(record(reliability=reliability("ATTENTION"))).as_dict()
        self.assertEqual(out["component_tokens"][1], "ATTENTION")


if __name__ == "__main__":
    unittest.main()
