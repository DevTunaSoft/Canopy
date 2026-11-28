"""Synthetic, offline verification of the native suspend/resume contract.

These tests exercise pure records, parsers and the composed read-only adapter.
They are SYNTHETIC: no real suspend, resume, D-Bus, Plasma session or guest
was used. Run with the repository root on PYTHONPATH:

  PYTHONPATH=<repo> python -m unittest discover -s tools/session_recovery -p 'test_*.py' -v
"""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from canopy_core.host_events import PROTOCOL_VERSION, HostEvent
from canopy_features.reliability.lock_session_events import SessionState
from canopy_features.session_recovery.contracts import (
    CHECKPOINTS, EVIDENCE_LABELS, MAX_CHECKPOINTS, OUTCOMES, STATIC_SOURCE_ONLY,
    VERDICT_REASONS, Fallback, SessionRecoveryError, StateCapture, Verdict)
from canopy_features.session_recovery.logind_upower import (
    DAEMON, NO_NEW_SERVICE, POLL_INTERVAL_SECONDS, parse_logind_show_session,
    parse_plasma_state, parse_upower_info)
from canopy_features.session_recovery.native_integration import (
    PlasmaRecoveryIntegration)

SESSION_TOPIC = "session.state.changed"
ACTIVE = SessionState(False, False)


def _facts(value=True):
    return {key: value for key in (
        "shell_active", "dock_visible", "launcher_visible",
        "window_visible", "session_present", "workspace_stable")}


def _ready(label="NATIVE RUNTIME"):
    integration = PlasmaRecoveryIntegration()
    integration.observe_session_state(ACTIVE)
    integration.capture("pre", source="host-status-file", interface="logind",
                        facts=_facts())
    integration.mark_suspend(True, evidence_label=label)
    integration.mark_resume(True, evidence_label=label)
    integration.preserve(session_id_stable=True, work_area_stable=True,
                         windows_restored=True, source="host-status-file")
    integration.capture("post", source="host-status-file", interface="upower",
                        facts=_facts())
    integration.reobserve(True)
    return integration


class ContractTests(unittest.TestCase):
    def test_default_snapshot_is_blocked(self):
        verdict = PlasmaRecoveryIntegration().snapshot().verdict()
        self.assertEqual(verdict.outcome, "BLOCKED")
        self.assertEqual(verdict.reason, "native-evidence-absent")

    def test_synthetic_full_evidence_never_passes(self):
        integration = _ready("SYNTHETIC")
        verdict = integration.snapshot(evidence_label="SYNTHETIC").verdict()
        self.assertEqual(verdict.outcome, "BLOCKED")
        self.assertEqual(verdict.reason, "native-evidence-absent")

    def test_static_source_never_passes(self):
        verdict = _ready().snapshot(evidence_label=STATIC_SOURCE_ONLY).verdict()
        self.assertEqual(verdict.outcome, "BLOCKED")

    def test_suspend_unobserved_is_not_run(self):
        integration = PlasmaRecoveryIntegration()
        integration.observe_session_state(ACTIVE)
        integration.mark_suspend(False, evidence_label="NATIVE RUNTIME")
        self.assertEqual(
            integration.snapshot(evidence_label="NATIVE RUNTIME").verdict().reason,
            "suspend-not-observed")

    def test_resume_unobserved_is_not_run(self):
        integration = PlasmaRecoveryIntegration()
        integration.observe_session_state(ACTIVE)
        integration.mark_suspend(True, evidence_label="NATIVE RUNTIME")
        integration.mark_resume(False, evidence_label="NATIVE RUNTIME")
        self.assertEqual(
            integration.snapshot(evidence_label="NATIVE RUNTIME").verdict().reason,
            "resume-not-observed")

    def test_reobservation_owed_is_not_run(self):
        integration = _ready()
        integration.reobserve(False)
        self.assertEqual(
            integration.snapshot(evidence_label="NATIVE RUNTIME").verdict().reason,
            "desktop-not-reobserved")

    def test_partial_facts_are_not_run_not_fail(self):
        integration = PlasmaRecoveryIntegration()
        integration.observe_session_state(ACTIVE)
        partial = _facts()
        partial["dock_visible"] = None
        integration.capture("pre", source="host-status-file",
                            interface="logind", facts=partial)
        integration.mark_suspend(True, evidence_label="NATIVE RUNTIME")
        integration.mark_resume(True, evidence_label="NATIVE RUNTIME")
        integration.preserve(session_id_stable=True, work_area_stable=True,
                             windows_restored=True, source="host-status-file")
        integration.capture("post", source="host-status-file",
                            interface="logind", facts=_facts())
        integration.reobserve(True)
        verdict = integration.snapshot(evidence_label="NATIVE RUNTIME").verdict()
        self.assertEqual((verdict.outcome, verdict.reason),
                         ("NOT RUN", "pre-post-facts-incomplete"))

    def test_false_desktop_fact_fails(self):
        integration = _ready()
        post = _facts()
        post["window_visible"] = False
        integration.capture("post", source="host-status-file",
                            interface="logind", facts=post)
        verdict = integration.snapshot(evidence_label="NATIVE RUNTIME").verdict()
        self.assertEqual((verdict.outcome, verdict.reason),
                         ("FAIL", "desktop-state-not-restored"))

    def test_unknown_preservation_is_not_run(self):
        integration = _ready()
        integration.preserve(session_id_stable=None, work_area_stable=True,
                             windows_restored=True, source="host-status-file")
        verdict = integration.snapshot(evidence_label="NATIVE RUNTIME").verdict()
        self.assertEqual((verdict.outcome, verdict.reason),
                         ("NOT RUN", "preservation-incomplete"))

    def test_lost_work_is_fail(self):
        integration = _ready()
        integration.preserve(session_id_stable=True, work_area_stable=False,
                             windows_restored=False, source="host-status-file")
        verdict = integration.snapshot(evidence_label="NATIVE RUNTIME").verdict()
        self.assertEqual((verdict.outcome, verdict.reason),
                         ("FAIL", "session-or-work-not-preserved"))

    def test_full_native_observation_passes(self):
        verdict = _ready().snapshot(evidence_label="NATIVE RUNTIME").verdict()
        self.assertEqual((verdict.outcome, verdict.reason),
                         ("PASS", "native-suspend-resume-recovery-verified"))

    def test_verdict_direct_construction_refuses_non_native_pass(self):
        with self.assertRaises(SessionRecoveryError):
            Verdict("PASS", "native-suspend-resume-recovery-verified", "SYNTHETIC")

    def test_vocabularies_are_fixed(self):
        self.assertEqual(len(EVIDENCE_LABELS), 4)
        self.assertEqual(len(OUTCOMES), 4)
        self.assertEqual(len(VERDICT_REASONS), 10)
        self.assertEqual(len(CHECKPOINTS), MAX_CHECKPOINTS)

    def test_fallback_is_declaration_only(self):
        fallback = Fallback("native-evidence-absent")
        self.assertEqual(fallback.target, "stock-plasma")
        self.assertEqual(fallback.action, "none")
        self.assertIs(fallback.executed, False)
        with self.assertRaises(SessionRecoveryError):
            Fallback("not-a-reason")

    def test_fallback_never_executes(self):
        integration = _ready()
        fallback = integration.fallback("host-unavailable")
        self.assertIs(fallback.executed, False)
        self.assertIs(integration.availability().available, True)

    def test_capture_rejects_hostile_facts(self):
        with self.assertRaises(SessionRecoveryError):
            StateCapture("pre", "host-status-file", "logind", "all-visible")
        with self.assertRaises(SessionRecoveryError):
            StateCapture("pre", "untrusted", "logind", _facts())
        with self.assertRaises(SessionRecoveryError):
            StateCapture("unknown", "host-status-file", "logind", _facts())
        hostile = _facts()
        hostile["shell_active"] = "yes"
        with self.assertRaises(SessionRecoveryError):
            StateCapture("pre", "host-status-file", "logind", hostile)

    def test_capture_is_read_only_and_json_serializable(self):
        capture = StateCapture("pre", "host-status-file", "logind", _facts())
        with self.assertRaises(TypeError):
            capture.facts["shell_active"] = False
        json.dumps(capture.to_dict())
        json.dumps(_ready().snapshot(evidence_label="NATIVE RUNTIME").to_dict())

    def test_integration_type_guards(self):
        integration = PlasmaRecoveryIntegration()
        with self.assertRaises(SessionRecoveryError):
            integration.mark_suspend("yes")
        with self.assertRaises(SessionRecoveryError):
            integration.reobserve(1)
        with self.assertRaises(SessionRecoveryError):
            integration.preserve(session_id_stable=1, work_area_stable=True,
                                 windows_restored=True, source="host-status-file")
        with self.assertRaises(SessionRecoveryError):
            integration.capture("mid", source="host-status-file",
                                interface="logind", facts=_facts())

    def test_checkpoint_history_is_bounded(self):
        integration = _ready()
        for _ in range(MAX_CHECKPOINTS * 3):
            integration.reobserve(True)
        self.assertLessEqual(len(integration.view()["checkpoints"]), MAX_CHECKPOINTS)

    def test_boundary_loss_downgrades_to_static_and_declares_fallback(self):
        integration = _ready()
        integration._path.mark_host_unavailable()
        snapshot = integration.snapshot(evidence_label="NATIVE RUNTIME")
        self.assertEqual(snapshot.evidence_label, STATIC_SOURCE_ONLY)
        self.assertEqual(snapshot.verdict().outcome, "BLOCKED")
        self.assertEqual(snapshot.fallback.reason, "host-unavailable")

    def test_closed_integration_fails_closed(self):
        integration = _ready()
        integration.close()
        with self.assertRaises(SessionRecoveryError):
            integration.snapshot()
        self.assertEqual(integration._path.decide("read_status").available, False)

    def test_existing_host_event_path_is_reused(self):
        integration = PlasmaRecoveryIntegration()
        event = HostEvent(PROTOCOL_VERSION, SESSION_TOPIC, 1,
                          (("state", "active"),))
        report = integration.observe_event(event)
        self.assertEqual(report.processed, 1)
        self.assertTrue(integration.availability().available)


class ParserTests(unittest.TestCase):
    def test_logind_read_only_view(self):
        view = parse_logind_show_session(
            "Active=yes\nLockedHint=no\nState=active\nType=wayland\n")
        self.assertEqual(view.to_dict(), {"active": True, "locked": False,
                                          "state": "active",
                                          "session_type": "wayland"})

    def test_logind_unknown_value_is_not_guessed(self):
        view = parse_logind_show_session("Active=maybe\nState=active\n")
        self.assertIsNone(view.active)
        self.assertEqual(view.state, "active")

    def test_logind_duplicate_field_fails_closed(self):
        with self.assertRaises(SessionRecoveryError):
            parse_logind_show_session("Active=yes\nActive=no\n")

    def test_logind_bounds(self):
        with self.assertRaises(SessionRecoveryError):
            parse_logind_show_session("Active=yes\n" * 200)
        with self.assertRaises(SessionRecoveryError):
            parse_logind_show_session("x" * 300)

    def test_upower_view(self):
        view = parse_upower_info(
            "  state:              discharging\n  percentage:         42%\n")
        self.assertEqual(view.to_dict(), {"state": "discharging",
                                          "percentage": 42})

    def test_upower_hostile_values_are_unknown(self):
        view = parse_upower_info(
            "  state:              flying-cow\n  percentage:         900%\n")
        self.assertEqual(view.to_dict(), {"state": "unknown", "percentage": None})

    def test_plasma_state_token_validation(self):
        self.assertEqual(parse_plasma_state("state=locked\n").state, "locked")
        self.assertEqual(parse_plasma_state("state=ROOT\n").state, "unknown")

    def test_no_new_service_constants(self):
        self.assertIs(NO_NEW_SERVICE, True)
        self.assertIs(DAEMON, False)
        self.assertIsNone(POLL_INTERVAL_SECONDS)

    def test_read_only_probe_stays_static_and_writes_nothing(self):
        from probe_readonly import build_snapshot
        report = build_snapshot(logind_text="Active=yes\nLockedHint=no\n",
                                upower_text="  state: discharging\n")
        self.assertEqual(report["evidence_label"], "STATIC SOURCE ONLY")
        self.assertEqual(report["verdict"], {
            "outcome": "BLOCKED", "reason": "native-evidence-absent",
            "evidence_label": "STATIC SOURCE ONLY"})
        self.assertEqual((report["writes"], report["commands_executed"],
                          report["polls"]), (0, 0, 0))
        self.assertIs(report["fallback"]["executed"], False)


class StaticTests(unittest.TestCase):
    def test_no_daemon_or_io_imports_in_production_modules(self):
        root = Path(__file__).resolve().parents[2]
        package = root / "canopy_features" / "session_recovery"
        forbidden_imports = {"subprocess", "socket", "threading", "asyncio",
                             "dbus", "time", "os"}
        forbidden_calls = {"sleep", "poll", "select", "spawn", "Popen",
                           "system", "exec", "eval"}
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".")[0] for alias in node.names}
                    self.assertFalse(names & forbidden_imports, str(path))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0],
                                     forbidden_imports, str(path))
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden_calls, str(path))

    def test_tests_are_outside_ci_discovery_scope(self):
        # tests/ is not an owned path for this change: the new suite lives in
        # tools/session_recovery and is invoked explicitly, never via
        # `unittest discover -s tests`. This test records that boundary.
        self.assertTrue(str(Path(__file__).resolve()).replace("\\", "/").endswith(
            "tools/session_recovery/test_contracts.py"))


if __name__ == "__main__":
    unittest.main()
