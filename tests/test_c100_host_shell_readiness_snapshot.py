"""Contract tests for the pure shell readiness snapshot composition.

Run: python -m unittest tests.test_c100_host_shell_readiness_snapshot -v
"""
import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from types import MappingProxyType
import unittest

from canopy_features.host.shell_readiness_snapshot import (
    COMPONENTS, ReadinessError, ShellReadinessSnapshot, compose,
)
from canopy_features.performance.frame_pacing import parse_frame_times
from canopy_features.performance.performance_snapshot import compose_snapshot
from canopy_features.security.security_decision_snapshot import (
    SecurityDecisionSnapshot,
)

NEGATIVE_CLAIMS = (
    "release_approved", "linux_mint_acceptance_proven", "owner_visual_approval",
    "desktop_session_started", "shell_running", "process_launched",
    "measurement_performed", "real_hardware_measured", "installation_attempted",
)


def security():
    return SecurityDecisionSnapshot(
        schema=1, uri_status="PERMITTED", privilege_status="ALLOWED",
        privilege_reason="allowed", metadata_status="SAFE",
        metadata_capability_count=2,
    ).as_dict()


def reliability(status="OK"):
    return {
        "schema": 1, "status": status, "acceptance": "NOT_ESTABLISHED",
        "startup": {"action": "ready", "safe_to_start": True,
                    "needs_rollback": False, "completed_count": 3,
                    "unwind_count": 0, "reason": "SECRET_STARTUP_MARKER"},
        "delivery": {"sent": 2, "received": 2, "delivered": 2,
                     "duplicates": 0, "reordered": 0, "gaps": 0, "missed": 0,
                     "dropped": 0, "rejected": 0, "notice_count": 0,
                     "last_policy": "queue"},
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
        "performance": performance(), "installer": installer(), "window": window(),
    }
    base.update(overrides)
    return base


def compose_ok(rec):
    return compose(rec).as_dict()


class RealCompositionTests(unittest.TestCase):
    def test_five_real_records_compose(self):
        out = compose_ok(record())
        self.assertEqual(out["status"], "READINESS_SNAPSHOT")
        self.assertEqual(out["schema"], 1)
        self.assertEqual(out["component_count"], 5)
        self.assertEqual(out["component_tokens"],
                         ["SNAPSHOT", "OK", "VALID", "PLAN_SNAPSHOT", "OK"])

    def test_all_negative_claims_hardcoded(self):
        out = compose_ok(record())
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_mappingproxy_records_accepted(self):
        rec = record(
            reliability=MappingProxyType(reliability()),
            window=MappingProxyType(window()),
        )
        self.assertEqual(compose_ok(rec)["component_count"], 5)

    def test_blocked_statuses_preserved_as_fixed_tokens(self):
        out = compose_ok(record(reliability=reliability("BLOCKED"),
                                window=window("BLOCKED")))
        self.assertEqual(out["component_tokens"][1], "BLOCKED")
        self.assertEqual(out["component_tokens"][4], "BLOCKED")
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_attention_status_preserved(self):
        out = compose_ok(record(window=window("ATTENTION")))
        self.assertEqual(out["component_tokens"][4], "ATTENTION")

    def test_no_raw_value_echo(self):
        out = compose_ok(record())
        self.assertNotIn("SECRET_STARTUP_MARKER", json.dumps(out, sort_keys=True))

    def test_deterministic_bytes(self):
        rec = record()
        self.assertEqual(json.dumps(compose_ok(rec), sort_keys=True),
                         json.dumps(compose_ok(rec), sort_keys=True))

    def test_report_is_frozen(self):
        made = compose(record())
        with self.assertRaises(FrozenInstanceError):
            made.component_count = 0

    def test_as_dict_returns_fresh_container(self):
        made = compose(record())
        first = made.as_dict()
        first["component_tokens"][0] = "BLOCKED"
        self.assertEqual(made.as_dict()["component_tokens"][0], "SNAPSHOT")

    def test_all_five_components_required(self):
        for name in COMPONENTS:
            rec = record()
            del rec[name]
            with self.subTest(name=name), self.assertRaises(ReadinessError):
                compose(rec)


class IntegrityTests(unittest.TestCase):
    def test_non_dict_wrapper(self):
        for bad in (None, 7, [], "x", True):
            with self.subTest(bad=bad), self.assertRaises(ReadinessError):
                compose(bad)

    def test_extra_wrapper_key(self):
        with self.assertRaises(ReadinessError):
            compose(dict(record(), extra=1))

    def test_wrong_wrapper_schema(self):
        for bad in (0, 2, "1", True, None, []):
            rec = record()
            rec["schema"] = bad
            with self.subTest(bad=bad), self.assertRaises(ReadinessError):
                compose(rec)

    def test_security_claim_flip_rejected(self):
        sec = security()
        sec["measurement_performed"] = True
        with self.assertRaises(ReadinessError):
            compose(record(security=sec))

    def test_installer_claim_flip_rejected(self):
        inst = installer()
        inst["package_installed"] = True
        with self.assertRaises(ReadinessError):
            compose(record(installer=inst))

    def test_wrong_component_status_rejected(self):
        for name, key, bad in (
            ("security", "uri_status", "APPROVED"),
            ("reliability", "status", "APPROVED"),
            ("installer", "icon_status", "EXECUTED"),
            ("window", "status", "APPROVED"),
        ):
            rec = record()
            rec[name][key] = bad
            with self.subTest(name=name), self.assertRaises(ReadinessError):
                compose(rec)

    def test_unhashable_component_token_rejected(self):
        rec = record()
        rec["reliability"]["status"] = []
        with self.assertRaises(ReadinessError):
            compose(rec)

    def test_missing_nested_key_rejected(self):
        rec = record()
        del rec["reliability"]["startup"]["reason"]
        with self.assertRaises(ReadinessError):
            compose(rec)

    def test_oversized_nested_collection_rejected(self):
        rec = record()
        rec["window"]["switcher"]["order"] = tuple(range(129))
        with self.assertRaises(ReadinessError):
            compose(rec)

    def test_oversized_nested_text_rejected(self):
        rec = record()
        rec["reliability"]["startup"]["reason"] = "x" * 5000
        with self.assertRaises(ReadinessError):
            compose(rec)

    def test_negative_count_rejected(self):
        rec = record()
        rec["security"]["metadata_capability_count"] = -1
        with self.assertRaises(ReadinessError):
            compose(rec)

    def test_performance_artifact_rejected(self):
        perf = performance()
        perf["measurement_performed"] = True
        with self.assertRaises(ReadinessError):
            compose(record(performance=perf))

    def test_subvalidator_detail_not_echoed(self):
        perf = performance()
        perf["linux_mint_acceptance"] = "SECRET_PERF_MARKER"
        with self.assertRaises(ReadinessError) as ctx:
            compose(record(performance=perf))
        self.assertNotIn("SECRET_PERF_MARKER", str(ctx.exception))

    def test_error_messages_are_fixed_tokens(self):
        rec = record()
        rec["security"]["uri_status"] = "SENTINEL_URL_MARKER"
        with self.assertRaises(ReadinessError) as ctx:
            compose(rec)
        self.assertEqual(str(ctx.exception), "uri status token is unsupported")
        self.assertNotIn("SENTINEL_URL_MARKER", str(ctx.exception))


class ForgedRecordTests(unittest.TestCase):
    def make(self, **overrides):
        values = dict(schema=1, component_count=5,
                      component_tokens=("SNAPSHOT", "OK", "VALID",
                                        "PLAN_SNAPSHOT", "OK"))
        values.update(overrides)
        return ShellReadinessSnapshot(**values)

    def test_forged_record_cannot_claim_approval(self):
        out = self.make().as_dict()
        for key in NEGATIVE_CLAIMS:
            self.assertIs(out[key], False)

    def test_bad_tokens_fail_closed(self):
        for bad in ((), ["OK"] * 5, ("APPROVED",) * 5, None, [], "x"):
            with self.subTest(bad=str(bad)[:30]), self.assertRaises(ReadinessError):
                self.make(component_tokens=bad).as_dict()

    def test_unhashable_token_fails_closed(self):
        tokens = ["OK"] * 5
        tokens[0] = []
        with self.assertRaises(ReadinessError):
            self.make(component_tokens=tuple(tokens)).as_dict()

    def test_bad_counts_fail_closed(self):
        for bad in (-1, 6, True, "5", None):
            with self.subTest(bad=bad), self.assertRaises(ReadinessError):
                self.make(component_count=bad).as_dict()
            with self.subTest(schema=bad), self.assertRaises(ReadinessError):
                self.make(schema=bad).as_dict()


class PurityTests(unittest.TestCase):
    def test_no_io_exec_or_visual_imports(self):
        module_file = Path(__file__).resolve().parents[1] / (
            "canopy_features/host/shell_readiness_snapshot.py")
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
        allowed = {"collections", "dataclasses", "tools"}
        forbidden = {
            "os", "time", "random", "subprocess", "socket", "threading",
            "datetime", "multiprocessing", "ctypes", "pathlib", "importlib",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(top, forbidden)
                    self.assertIn(top, allowed)
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                self.assertNotIn(top, forbidden)
                self.assertIn(top, allowed)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, {"system", "popen", "Popen",
                                                  "open", "geteuid"})

    def test_only_pure_validator_composed(self):
        module_file = Path(__file__).resolve().parents[1] / (
            "canopy_features/host/shell_readiness_snapshot.py")
        source = module_file.read_text(encoding="utf-8")
        self.assertIn("perf_snapshot_artifact_validator", source)
        for name in ("subprocess", "os.system", "QApplication", "QML"):
            self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
