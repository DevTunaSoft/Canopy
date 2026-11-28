"""Synthetic RED/GREEN tests for bounded native quick controls (M3).

Run from the worktree root with:
  PYTHONPATH=. python -m unittest discover -s scratch/native_quick_controls/tests -p 'test_*.py'
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from canopy_features.quick_controls import native_controls as m
from canopy_features.system import quick_controls_state as qcs
from canopy_features.system import session_controls_native as session_native


class PlanTests(unittest.TestCase):
    def test_plan_fields_come_from_fixed_allowlists(self):
        plan = m.CommandPlan("set-brightness", (42,))
        self.assertEqual(plan.bus, "session")
        self.assertEqual(plan.service, "org.kde.Solid.PowerManagement")
        self.assertEqual(
            plan.object_path,
            "/org/kde/Solid/PowerManagement/Actions/BrightnessControl",
        )
        self.assertEqual(plan.method, "setBrightness")
        payload = plan.to_dict()
        self.assertFalse(payload["executed"])
        self.assertNotIn("argv", json.dumps(payload))
        payload["args"] = (99,)
        self.assertEqual(plan.args, (42,))

    def test_read_plans_take_no_arguments(self):
        for key in ("recheck-connectivity", "query-power-capability"):
            with self.subTest(key=key):
                self.assertEqual(m.CommandPlan(key, ()).args, ())
                with self.assertRaises(m.NativeControlsError):
                    m.CommandPlan(key, (1,))

    def test_hostile_plan_input_is_rejected(self):
        for args in (
            ("rm-rf", ()), ("set-brightness", (-1,)),
            ("set-brightness", (m.MAX_BRIGHTNESS + 1,)),
            ("set-brightness", [10]), ("set-brightness", ("10",)),
            ("set-brightness", (1, 2)), ("recheck-connectivity", ()),
        ):
            with self.subTest(args=args):
                if args == ("recheck-connectivity", ()):
                    m.CommandPlan(*args)
                else:
                    with self.assertRaises(m.NativeControlsError):
                        m.CommandPlan(*args)


class ProbeFactTests(unittest.TestCase):
    def test_defaults_are_unprobed_not_false(self):
        facts = m.ProbeFacts()
        self.assertIsNone(facts.brightness_supported)
        self.assertIsNone(facts.backlight_device)
        self.assertIsNone(facts.connectivity_check_available)
        self.assertIsNone(facts.network_control_permission)
        self.assertIsNone(facts.power_can_suspend)

    def test_hostile_source_and_tokens_are_rejected(self):
        hostile = (
            dict(source="../../etc/passwd"),
            dict(source="x" * (m.MAX_SOURCE_BYTES + 1)),
            dict(source=None),
            dict(brightness_supported="false"),
            dict(brightness_max=-1),
            dict(brightness_value=10, brightness_max=9),
            dict(network_state=9999),
            dict(connectivity=99),
            dict(network_control_permission="sudo"),
            dict(power_can_suspend="maybe"),
        )
        for fields in hostile:
            with self.subTest(fields=fields):
                with self.assertRaises(m.NativeControlsError):
                    m.ProbeFacts(**fields)


class BrightnessTests(unittest.TestCase):
    def test_no_probe_is_not_run(self):
        verdict = m.NativeControls.brightness_step(5, m.ProbeFacts())
        self.assertEqual(verdict.execution, m.EXECUTION_NOT_RUN)
        self.assertEqual(verdict.reason, qcs.REASON_NO_CAPABILITY_PROBE)
        self.assertIsNone(verdict.plan)
        self.assertEqual(verdict.availability, qcs.UNAVAILABLE)
        self.assertIn("NOT_RUN", verdict.label)

    def test_absent_capability_is_not_run(self):
        verdict = m.NativeControls.brightness_step(
            5, m.ProbeFacts(brightness_supported=False, backlight_device=False,
                            brightness_value=50, brightness_max=100,
                            source="plasma-probe"))
        self.assertEqual(verdict.execution, m.EXECUTION_NOT_RUN)
        self.assertEqual(verdict.reason, qcs.REASON_CAPABILITY_ABSENT)
        self.assertIsNone(verdict.plan)

    def test_bounded_step_clamps_to_range(self):
        facts = m.ProbeFacts(brightness_supported=True, backlight_device=True,
                             brightness_value=95, brightness_max=100)
        verdict = m.NativeControls.brightness_step(50, facts)
        self.assertEqual(verdict.reason, qcs.REASON_OK)
        self.assertEqual(verdict.plan.args, (100,))
        self.assertEqual(verdict.execution, m.EXECUTION_NOT_RUN)
        self.assertEqual(verdict.availability, qcs.AVAILABLE)
        lower = m.NativeControls.brightness_step(-100, facts)
        self.assertEqual(lower.plan.args, (0,))

    def test_zero_and_overflow_deltas_are_refused(self):
        facts = m.ProbeFacts()
        for delta in (101, -101, True, 1.5, "5"):
            with self.subTest(delta=delta):
                with self.assertRaises(m.NativeControlsError):
                    m.NativeControls.brightness_step(delta, facts)

    def test_no_change_has_no_plan(self):
        zero = m.NativeControls.brightness_step(0, m.ProbeFacts())
        self.assertEqual(zero.reason, qcs.REASON_NO_CHANGE)
        self.assertIsNone(zero.plan)
        facts = m.ProbeFacts(brightness_supported=True, backlight_device=True,
                             brightness_value=100, brightness_max=100)
        verdict = m.NativeControls.brightness_step(5, facts)
        self.assertEqual(verdict.reason, qcs.REASON_NO_CHANGE)
        self.assertIsNone(verdict.plan)


class NetworkTests(unittest.TestCase):
    def test_permission_denial_is_blocked(self):
        facts = m.ProbeFacts(connectivity_check_available=False,
                             network_control_permission="auth",
                             network_state=70, connectivity=4,
                             source="plasma-probe")
        verdict = m.NativeControls.network_recheck(facts)
        self.assertEqual(verdict.execution, m.EXECUTION_BLOCKED)
        self.assertEqual(verdict.reason, qcs.REASON_CAPABILITY_DENIED)
        self.assertIsNone(verdict.plan)
        self.assertIn("BLOCKED", verdict.label)

    def test_missing_capability_is_not_run(self):
        verdict = m.NativeControls.network_recheck(m.ProbeFacts(
            connectivity_check_available=False,
            network_control_permission="yes"))
        self.assertEqual(verdict.execution, m.EXECUTION_NOT_RUN)
        self.assertEqual(verdict.reason, qcs.REASON_CAPABILITY_ABSENT)

    def test_allowed_permission_yields_one_static_plan(self):
        verdict = m.NativeControls.network_recheck(m.ProbeFacts(
            connectivity_check_available=True,
            network_control_permission="yes"))
        self.assertEqual(verdict.plan.method, "CheckConnectivity")
        self.assertEqual(verdict.plan.args, ())
        self.assertEqual(verdict.availability, qcs.AVAILABLE)
        self.assertEqual(verdict.execution, m.EXECUTION_NOT_RUN)


class PowerTests(unittest.TestCase):
    def test_logind_denial_is_blocked(self):
        facts = m.ProbeFacts(power_can_suspend="challenge",
                             power_list_jobs_allowed=False,
                             source="plasma-probe")
        verdict = m.NativeControls.power_capability(facts)
        self.assertEqual(verdict.execution, m.EXECUTION_BLOCKED)
        self.assertEqual(verdict.reason, qcs.REASON_CAPABILITY_DENIED)
        self.assertIsNone(verdict.plan)

    def test_missing_capability_is_not_run(self):
        verdict = m.NativeControls.power_capability(m.ProbeFacts(
            power_can_suspend="na", power_list_jobs_allowed=False))
        self.assertEqual(verdict.execution, m.EXECUTION_NOT_RUN)
        self.assertEqual(verdict.reason, qcs.REASON_CAPABILITY_ABSENT)

    def test_transitions_are_always_refused(self):
        for action in sorted(m.PRIVILEGED_TRANSITIONS):
            with self.subTest(action=action):
                verdict = m.NativeControls.refuse_transition(action)
                self.assertEqual(verdict.execution, m.EXECUTION_NOT_RUN)
                self.assertEqual(verdict.reason,
                                 qcs.REASON_PRIVILEGED_HOST_CHANGE)
                self.assertIsNone(verdict.plan)
        with self.assertRaises(m.NativeControlsError):
            m.NativeControls.refuse_transition("reboot; rm -rf /")


class HostResultTests(unittest.TestCase):
    def test_pass_requires_plan_and_host_success(self):
        verdict = m.NativeControls.network_recheck(m.ProbeFacts(
            connectivity_check_available=True,
            network_control_permission="yes"))
        passed = m.NativeControls.host_result(
            verdict, m.EXECUTION_PASS, succeeded=True)
        self.assertEqual(passed.execution, m.EXECUTION_PASS)
        self.assertEqual(passed.reason, qcs.REASON_OK)
        for bad in (
            (verdict, m.EXECUTION_PASS, False),
            (verdict, m.EXECUTION_BLOCKED, True),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(m.NativeControlsError):
                    m.NativeControls.host_result(bad[0], bad[1],
                                                 succeeded=bad[2])
        blocked = m.NativeControls.network_recheck(m.ProbeFacts(
            connectivity_check_available=False,
            network_control_permission="auth"))
        with self.assertRaises(m.NativeControlsError):
            m.NativeControls.host_result(blocked, m.EXECUTION_PASS,
                                         succeeded=True)

    def test_not_run_never_claims_success(self):
        verdict = m.NativeControls.brightness_step(5, m.ProbeFacts())
        with self.assertRaises(m.NativeControlsError):
            m.NativeControls.host_result(verdict, m.EXECUTION_NOT_RUN,
                                         succeeded=True)
        stays = m.NativeControls.host_result(verdict, m.EXECUTION_NOT_RUN)
        self.assertEqual(stays.execution, m.EXECUTION_NOT_RUN)


class VerdictAndBoundaryTests(unittest.TestCase):
    def test_verdict_dict_is_fresh_bounded_and_serialisable(self):
        verdict = m.NativeControls.network_recheck(m.ProbeFacts(
            connectivity_check_available=True,
            network_control_permission="yes"))
        payload = verdict.to_dict()
        self.assertLess(len(json.dumps(payload, ensure_ascii=True)), 4096)
        self.assertFalse(payload["executed"])
        self.assertIn("NOT_RUN", payload["execution_label"])
        payload["plan"]["method"] = "PowerOff"
        self.assertEqual(verdict.plan.method, "CheckConnectivity")
        with self.assertRaises(m.NativeControlsError):
            m.ControlVerdict("brightness", "x", m.EXECUTION_PASS,
                             qcs.REASON_OK, None)

    def test_session_privileged_decisions_stay_not_run(self):
        path = session_native.SessionControlsNativePath()
        decision = path.decide("logout", None, None)
        self.assertEqual(decision.execution_label,
                         session_native.SESSION_EXECUTION_NOT_RUN)
        self.assertEqual(decision.to_dict()["execution_label"],
                         m.EXECUTION_NOT_RUN)
        self.assertFalse(decision.to_dict()["executed"])
        self.assertEqual(m.NativeControls.session_execution(decision),
                         m.EXECUTION_NOT_RUN)
        with self.assertRaises(m.NativeControlsError):
            m.NativeControls.session_execution("logout")

    def test_no_execution_or_transport_imports(self):
        import ast
        tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertLessEqual(imported, {
            "__future__", "dataclasses", "re", "types", "typing",
            "canopy_features.system.quick_controls_state",
            "canopy_features.system.session_controls_native",
            "canopy_features.system",
        })


if __name__ == "__main__":
    unittest.main()
