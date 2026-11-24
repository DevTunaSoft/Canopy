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
    "desktop_claim", "window_geometry_read",
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


def focus(status="OK"):
    return {
        "schema": 1, "status": status, "acceptance": "NOT_ESTABLISHED",
        "observation": "NOT_PERFORMED",
        "focus": {"live_windows": 1, "grant_count": 1, "decision_count": 1,
                  "statuses": ("GRANTED",), "target_apps": ("app",),
                  "reasons": ("ok",)},
        "workspace": {"workspace_count": 1, "identifiers": ("w1",),
                      "problem_count": 0, "problem_reasons": ()},
        "switcher": {"active": True, "current": "w1", "selected": "w1",
                     "window_count": 1, "order": ("w1",)},
    }


def session(status="OK"):
    return {
        "schema": 1, "status": status, "acceptance": "NOT_ESTABLISHED",
        "switcher": {"active": True, "current": "w1", "selected": "w1",
                     "window_count": 1, "order": ("w1",)},
        "workspace": {"workspace_count": 1, "identifiers": ("w1",),
                      "problem_count": 0, "problem_reasons": ()},
        "portal": {"capability_count": 1, "denied": (), "missing": (),
                   "session_type": "x11", "unknown_permission": (),
                   "usable": True, "wayland": False,
                   "window_enumeration": "SUPPORTED"},
        "negotiation": {"backend": "x11", "granted": True,
                        "status": "OK", "supported": True},
    }


def recovery(status="OK"):
    return {
        "schema": 1, "status": status, "acceptance": "NOT_ESTABLISHED",
        "observation": "NOT_PERFORMED",
        "startup": {"action": "ready", "safe_to_start": True,
                    "needs_rollback": False, "completed_count": 1,
                    "unwind_count": 0, "reason": "SECRET_RECOVERY_MARKER"},
        "session": {"accepted": True, "label": "default", "locked": False,
                    "recent_statuses": ("OK",), "suspended": False},
        "delivery": {"sent": 1, "received": 1, "delivered": 1,
                     "duplicates": 0, "reordered": 0, "gaps": 0, "missed": 0,
                     "dropped": 0, "rejected": 0, "notice_count": 0,
                     "last_policy": "queue"},
    }


def desktop(status="READY"):
    return {
        "status": status, "reason": "ok", "declared_count": 1,
        "action_count": 1, "argv_length": 0,
        "claims": ["no_process_launched", "no_value_echo",
                   "no_shell_metacharacters", "no_field_codes",
                   "no_unapproved_action", "no_desktop_claim"],
    }


def records(**overrides):
    base = {"schema": SCHEMA, "reliability": reliability(),
            "readiness": readiness(), "security": security(),
            "launch": launch(), "focus": focus(), "session": session(),
            "recovery": recovery(), "desktop": desktop()}
    base.update(overrides)
    return base


def report(h=None, recs=None):
    h = h or host()
    return h.capability_report(recs or records()).as_dict()


class CompositionTests(unittest.TestCase):
    def test_eight_merged_records_compose(self):
        out = report()
        self.assertEqual(out["status"], "CAPABILITY_REPORT")
        self.assertEqual(out["schema"], SCHEMA)
        self.assertEqual(out["component_count"], 8)
        self.assertEqual(out["component_tokens"],
                         ["OK", "READINESS_SNAPSHOT", "SNAPSHOT", "SUCCEEDED",
                          "OK", "OK", "OK", "READY"])
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
        for marker in ("SECRET_STARTUP_MARKER", "SECRET_RECOVERY_MARKER", BASE,
                       "allowed", "w1", "x11", "default"):
            self.assertNotIn(marker, rendered)

    def test_forged_report_cannot_claim_approval(self):
        forged = HostCapabilityReport(
            1, False, False, 8,
            ("OK", "READINESS_SNAPSHOT", "SNAPSHOT", "SUCCEEDED",
             "OK", "OK", "OK", "READY"))
        for key in NEGATIVE_KEYS:
            self.assertIs(forged.as_dict()[key], False)


class IntegrityTests(unittest.TestCase):
    def test_bad_wrapper(self):
        for bad in (None, 7, [], "x", {}, dict(records(), extra=1)):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(CapabilityReportError):
                host().capability_report(bad)

    def test_missing_component(self):
        for name in ("reliability", "readiness", "security", "launch",
                     "focus", "session", "recovery", "desktop"):
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
        good = ("OK", "READINESS_SNAPSHOT", "SNAPSHOT", "SUCCEEDED",
                "OK", "OK", "OK", "READY")
        bad_desktop = good[:7] + ("APPROVED",)
        for tokens in ((), ("OK",) * 8, ("APPROVED",) * 8, None, [],
                       [1, 2, 3, 4, 5, 6, 7, 8], bad_desktop):
            rec = HostCapabilityReport(1, False, False, 4, tokens)
            with self.subTest(tokens=str(tokens)[:30]), \
                    self.assertRaises(CapabilityReportError):
                rec.as_dict()


class SecondBatchTests(unittest.TestCase):
    def test_status_tokens_preserved(self):
        for name, builder, value, index in (
                ("focus", focus, "ATTENTION", 4),
                ("session", session, "BLOCKED", 5),
                ("recovery", recovery, "ATTENTION", 6),
                ("desktop", desktop, "DENIED", 7)):
            with self.subTest(name=name):
                out = report(recs=records(**{name: builder(value)}))
                self.assertEqual(out["component_tokens"][index], value)

    def test_negative_claims_still_fixed(self):
        out = report(recs=records(focus=focus("BLOCKED"),
                                  desktop=desktop("DENIED")))
        for key in NEGATIVE_KEYS:
            self.assertIs(out[key], False)

    def test_wrong_acceptance_or_observation_fails(self):
        for name, key in (("focus", "acceptance"), ("focus", "observation"),
                          ("session", "acceptance"),
                          ("recovery", "acceptance"),
                          ("recovery", "observation")):
            rec = records()
            rec[name][key] = "APPROVED"
            with self.subTest(name=name, key=key), \
                    self.assertRaises(CapabilityReportError):
                host().capability_report(rec)

    def test_wrong_desktop_reason_or_claims_fail(self):
        for key, value in (("reason", "unknown"), ("claims", ["desktop_claim"]),
                           ("claims", ["no_process_launched"] * 7)):
            rec = records()
            rec["desktop"][key] = value
            with self.subTest(key=key), self.assertRaises(CapabilityReportError):
                host().capability_report(rec)

    def test_nested_view_pinning(self):
        for name, nested, key in (("focus", "focus", "live_windows"),
                                  ("session", "portal", "wayland"),
                                  ("recovery", "session", "accepted")):
            rec = records()
            del rec[name][nested][key]
            with self.subTest(name=name), self.assertRaises(CapabilityReportError):
                host().capability_report(rec)

    def test_schema_and_count_cap(self):
        for name in ("focus", "session", "recovery"):
            rec = records()
            rec[name]["schema"] = 2
            with self.subTest(name=name), self.assertRaises(CapabilityReportError):
                host().capability_report(rec)
        with self.assertRaises(CapabilityReportError):
            host().capability_report(dict(records(), ninth={}))

    def test_no_raw_value_echo_second_batch(self):
        rendered = json.dumps(report(), sort_keys=True)
        for marker in ("SECRET_RECOVERY_MARKER", "x11", "default"):
            self.assertNotIn(marker, rendered)


class PurityTests(unittest.TestCase):
    def test_no_new_imports_or_process_launch(self):
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


class TestHygieneTests(unittest.TestCase):
    def test_no_unused_locals_in_capability_test_modules(self):
        """Dead locals in test scaffolding obscure the contract under test."""
        roots = Path(__file__).resolve().parents[1]
        modules = (
            "tests/test_core_shell_host_capability_report.py",
            "tests/test_core_shell_host_capabilities_event.py",
            "tests/test_core_capability_cli.py",
        )
        findings = []
        for rel in modules:
            tree = ast.parse((roots / rel).read_text(encoding="utf-8"))
            for fn in (n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
                loads = {n.id for n in ast.walk(fn)
                         if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                for node in ast.walk(fn):
                    if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
                            and node.id != "_" and node.id not in loads):
                        findings.append(f"{rel}:{node.lineno} {fn.name}:{node.id}")
        self.assertEqual(findings, [], "unused locals: " + ", ".join(findings))


if __name__ == "__main__":
    unittest.main()
