"""Contract tests for ShellHost's read-only capability report.

Run: python -m unittest tests.test_core_shell_host_capability_report -v
"""
import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import (
    CapabilityReportError, HostCapabilityReport, ShellHost,
)
from canopy_features.apps.launch_outcome_reconciler import (
    FIXED_CLAIMS as LAUNCH_CLAIMS, REASON_OK, STATUS_SUCCEEDED,
    LaunchOutcomeSnapshot,
)
from canopy_features.host.shell_readiness_snapshot import (
    ShellReadinessSnapshot,
)
from canopy_features.security.security_decision_snapshot import (
    SecurityDecisionSnapshot,
)

SCHEMA = 1
BASE = "integration/canopy-classic-20261123"
NEGATIVE_KEYS = (
    "release_approved", "linux_mint_acceptance_proven", "owner_visual_approval",
    "process_launched", "io_performed", "capability_activated",
    "desktop_session_started", "measurement_performed", "real_hardware_measured",
)


def host():
    pack = ShellPackInfo(
        pack_id="com.example.classic", name="classic", description="test pack",
        directory=Path("/nonexecuted/classic"), entrypoint="ui/Main.qml",
        shell_api=1, ui_engine="qt-qml", capabilities=frozenset({"dock"}))
    return ShellHost(PackScan((pack,), (), 1), {}, frozenset({"dock"}))


def reliability(status="OK"):
    return {
        "schema": 1, "status": status, "acceptance": "NOT_ESTABLISHED",
        "startup": {"action": "ready", "safe_to_start": True,
                    "needs_rollback": False, "completed_count": 1,
                    "unwind_count": 0, "reason": "SECRET_STARTUP_MARKER"},
        "delivery": {"sent": 1, "received": 1, "delivered": 1,
                     "duplicates": 0, "reordered": 0, "gaps": 0, "missed": 0,
                     "dropped": 0, "rejected": 0, "notice_count": 0,
                     "last_policy": "queue"},
        "switcher": {"active": True, "current": "w1", "selected": "w1",
                     "window_count": 1, "order": ("w1",)},
    }


def readiness():
    return ShellReadinessSnapshot(
        schema=1, component_count=5,
        component_tokens=("SNAPSHOT", "OK", "VALID", "PLAN_SNAPSHOT", "OK"),
    ).as_dict()


def security():
    return SecurityDecisionSnapshot(
        schema=1, uri_status="PERMITTED", privilege_status="ALLOWED",
        privilege_reason="allowed", metadata_status="SAFE",
        metadata_capability_count=2,
    ).as_dict()


def launch(status=STATUS_SUCCEEDED):
    return LaunchOutcomeSnapshot(
        status=status, reason=REASON_OK, event_count=1, relevant_count=1,
        success_count=1, failure_count=0, retry_count=0,
        claims=tuple(LAUNCH_CLAIMS),
    ).to_dict()


def records(**overrides):
    base = {"schema": SCHEMA, "reliability": reliability(),
            "readiness": readiness(), "security": security(),
            "launch": launch()}
    base.update(overrides)
    return base


def report(h=None, recs=None):
    h = h or host()
    return h.capability_report(recs or records()).as_dict()


class CompositionTests(unittest.TestCase):
    def test_four_merged_records_compose(self):
        out = report()
        self.assertEqual(out["status"], "CAPABILITY_REPORT")
        self.assertEqual(out["schema"], SCHEMA)
        self.assertEqual(out["component_count"], 4)
        self.assertEqual(out["component_tokens"],
                         ["OK", "READINESS_SNAPSHOT", "SNAPSHOT", "SUCCEEDED"])
        self.assertIs(out["has_active_pack"], False)
        self.assertIs(out["needs_recovery"], False)

    def test_negative_claims_hardcoded(self):
        out = report()
        for key in NEGATIVE_KEYS:
            self.assertIs(out[key], False)

    def test_reliability_status_token_preserved(self):
        out = report(recs=records(reliability=reliability("BLOCKED")))
        self.assertEqual(out["component_tokens"][0], "BLOCKED")

    def test_launch_status_token_preserved(self):
        out = report(recs=records(launch=launch("RETRY")))
        self.assertEqual(out["component_tokens"][3], "RETRY")

    def test_read_only_no_host_mutation(self):
        h = host()
        before = (h.active_id, h.needs_recovery, h.audit_snapshot())
        h.capability_report(records())
        self.assertEqual((h.active_id, h.needs_recovery), before[:2])
        self.assertEqual(h.audit_snapshot(), before[2])

    def test_frozen_and_fresh(self):
        made = host().capability_report(records())
        with self.assertRaises(FrozenInstanceError):
            made.component_count = 0
        first = made.as_dict()
        first["component_tokens"][0] = "BLOCKED"
        self.assertEqual(made.as_dict()["component_tokens"][0], "OK")

    def test_deterministic(self):
        self.assertEqual(json.dumps(report(), sort_keys=True),
                         json.dumps(report(), sort_keys=True))

    def test_no_raw_value_echo(self):
        rendered = json.dumps(report(), sort_keys=True)
        for marker in ("SECRET_STARTUP_MARKER", BASE, "allowed", "w1"):
            self.assertNotIn(marker, rendered)

    def test_forged_report_cannot_claim_approval(self):
        forged = HostCapabilityReport(1, False, False, 4,
                                      ("OK", "READINESS_SNAPSHOT", "SNAPSHOT",
                                       "SUCCEEDED"))
        for key in NEGATIVE_KEYS:
            self.assertIs(forged.as_dict()[key], False)


class IntegrityTests(unittest.TestCase):
    def test_bad_wrapper(self):
        for bad in (None, 7, [], "x", {}, dict(records(), extra=1)):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(CapabilityReportError):
                host().capability_report(bad)

    def test_missing_component(self):
        for name in ("reliability", "readiness", "security", "launch"):
            rec = records()
            del rec[name]
            with self.subTest(name=name), self.assertRaises(CapabilityReportError):
                host().capability_report(rec)

    def test_wrong_schema(self):
        for bad in (0, 2, "1", True, None):
            rec = records()
            rec["schema"] = bad
            with self.subTest(bad=bad), self.assertRaises(CapabilityReportError):
                host().capability_report(rec)

    def test_flipped_negative_claim(self):
        for component, key in (("readiness", "shell_running"),
                               ("security", "release_approved")):
            rec = records()
            rec[component][key] = True
            with self.subTest(component=component), \
                    self.assertRaises(CapabilityReportError):
                host().capability_report(rec)

    def test_wrong_status_token(self):
        for component, key in (("reliability", "status"),
                               ("readiness", "status"),
                               ("security", "status"),
                               ("launch", "status")):
            rec = records()
            rec[component][key] = "APPROVED"
            with self.subTest(component=component), \
                    self.assertRaises(CapabilityReportError):
                host().capability_report(rec)

    def test_unhashable_token_fails_closed(self):
        rec = records()
        rec["reliability"]["status"] = []
        with self.assertRaises(CapabilityReportError):
            host().capability_report(rec)

    def test_missing_nested_key(self):
        rec = records()
        del rec["reliability"]["switcher"]["window_count"]
        with self.assertRaises(CapabilityReportError):
            host().capability_report(rec)

    def test_oversized_nested_collection(self):
        rec = records()
        rec["reliability"]["switcher"]["order"] = tuple(range(129))
        with self.assertRaises(CapabilityReportError):
            host().capability_report(rec)

    def test_bad_launch_claims(self):
        rec = records()
        rec["launch"]["claims"] = ["release_approved"]
        with self.assertRaises(CapabilityReportError):
            host().capability_report(rec)

    def test_error_does_not_echo(self):
        rec = records()
        rec["reliability"]["status"] = "SENTINEL_MARKER"
        with self.assertRaises(CapabilityReportError) as ctx:
            host().capability_report(rec)
        self.assertNotIn("SENTINEL_MARKER", str(ctx.exception))

    def test_forged_bad_tokens_fail_closed(self):
        for tokens in ((), ("OK",) * 4, ("APPROVED",) * 4, None, [], [1, 2, 3, 4]):
            rec = HostCapabilityReport(1, False, False, 4, tokens)
            with self.subTest(tokens=str(tokens)[:30]), \
                    self.assertRaises(CapabilityReportError):
                rec.as_dict()


class PurityTests(unittest.TestCase):
    def test_no_new_imports_or_process_launch(self):
        source = Path(ShellHost.__module__.replace(".", "/")).with_suffix("")
        module_file = Path(__file__).resolve().parents[1] / "canopy_core/shell_host.py"
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
        forbidden = {"subprocess", "socket", "time", "random", "importlib"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], forbidden)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, {"system", "popen", "Popen", "exec"})


if __name__ == "__main__":
    unittest.main()
