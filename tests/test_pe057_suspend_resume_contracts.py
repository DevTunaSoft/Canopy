"""Offline source-contract tests for fail-closed suspend/resume availability.

No real suspend, resume, login, D-Bus, VM, Qt or compiled UI is exercised.
Every event is constructed in process from the existing host event primitive.
"""
import unittest
from pathlib import Path

from canopy_core.host_events import TOPICS, HostEvent
from canopy_features.reliability.lock_session_events import Reconciler, SessionEvent
from canopy_features.system.quick_controls_state import STATUS_TOKENS


def host_event(state, sequence=1, topic="session.state.changed"):
    """Build a delivered host event using only the existing v2 primitive."""
    return HostEvent(2, topic, sequence, (("state", state),))


class SuspendResumeContractTests(unittest.TestCase):
    def setUp(self):
        from canopy_features.reliability import suspend_resume_contracts as m
        self.m = m

    def test_contract_reuses_existing_host_event_vocabulary(self):
        self.assertIn(self.m.SESSION_TOPIC, TOPICS)
        self.assertEqual(self.m.SESSION_STATES, STATUS_TOKENS["session"])

    def test_empty_state_is_unknown_and_everything_unavailable(self):
        contracts = self.m.empty()
        self.assertEqual(contracts.phase, self.m.PHASE_UNKNOWN)
        for operation in self.m.OPERATIONS:
            decision = contracts.decide(operation)
            self.assertFalse(decision.available)
            self.assertEqual(decision.reason, self.m.REASON_UNKNOWN)
            self.assertTrue(decision.disclosure)

    def test_suspended_event_makes_all_operations_unavailable(self):
        contracts = self.m.empty().observe(host_event("suspended"))
        self.assertEqual(contracts.phase, self.m.PHASE_SUSPENDED)
        for operation in self.m.OPERATIONS:
            decision = contracts.decide(operation)
            self.assertFalse(decision.available)
            self.assertEqual(decision.reason, self.m.REASON_SUSPENDED)

    def test_resume_event_requires_explicit_reobservation(self):
        suspended = self.m.empty().observe(host_event("suspended"))
        resumed = suspended.observe(host_event("active", sequence=2))
        self.assertEqual(resumed.phase, self.m.PHASE_RESUME_PENDING)
        self.assertFalse(resumed.decide("launch_app").available)
        self.assertEqual(resumed.decide("launch_app").reason,
                         self.m.REASON_RESUME_PENDING)

        ready = resumed.resume_ready()
        self.assertEqual(ready.phase, self.m.PHASE_ACTIVE)
        decision = ready.decide("launch_app")
        self.assertTrue(decision.available)
        self.assertEqual(decision.reason, self.m.REASON_OK)

    def test_resume_ready_cannot_fire_from_suspended_or_unknown(self):
        for contracts in (self.m.empty(),
                          self.m.empty().observe(host_event("suspended"))):
            with self.assertRaises(self.m.SuspendResumeError):
                contracts.resume_ready()

    def test_malformed_observed_data_degrades_without_raising(self):
        bad_events = (
            host_event(None),
            host_event("sleeping"),
            host_event(7),
            HostEvent(2, "session.state.changed", 3, ()),
        )
        for event in bad_events:
            contracts = self.m.empty().observe(event)
            self.assertEqual(contracts.phase, self.m.PHASE_UNKNOWN)
            self.assertFalse(contracts.decide("launch_app").available)

    def test_wrong_event_type_or_topic_is_a_caller_contract_error(self):
        with self.assertRaises(self.m.SuspendResumeError):
            self.m.empty().observe({"state": "suspended"})
        with self.assertRaises(self.m.SuspendResumeError):
            self.m.empty().observe(
                host_event("suspended", topic="capabilities.report"))

    def test_older_event_cannot_regress_suspended_state(self):
        suspended = self.m.empty().observe(host_event("suspended", sequence=9))
        stale = suspended.observe(host_event("active", sequence=4))
        self.assertIs(stale, suspended)
        self.assertEqual(stale.phase, self.m.PHASE_SUSPENDED)

    def test_composes_with_existing_lock_session_reconciler(self):
        reconciler = Reconciler(initial_locked=False)
        reconciler.observe(SessionEvent("suspend", 10, "logind"))
        suspended = self.m.empty().from_session_state(reconciler.state)
        self.assertEqual(suspended.phase, self.m.PHASE_SUSPENDED)

        reconciler.observe(SessionEvent("resume", 20, "logind"))
        reconciler.observe(SessionEvent("unlock", 30, "logind"))
        resumed = suspended.from_session_state(reconciler.state)
        self.assertEqual(resumed.phase, self.m.PHASE_RESUME_PENDING)
        self.assertFalse(resumed.decide("open_settings").available)
        self.assertTrue(resumed.resume_ready().decide("open_settings").available)

    def test_session_state_flags_are_read_not_overridden(self):
        class Forged:
            suspended = False
            locked = False

            @property
            def label(self):
                return "active"

        with self.assertRaises(self.m.SuspendResumeError):
            self.m.empty().from_session_state(Forged())

    def test_invalid_operation_is_unavailable(self):
        active = self.m.empty().observe(host_event("active"))
        self.assertEqual(active.phase, self.m.PHASE_ACTIVE)
        for operation in (None, 7, "suspend", "rm -rf", "launch_app;"):
            decision = active.decide(operation)
            self.assertFalse(decision.available)
            self.assertEqual(decision.reason, self.m.REASON_INVALID_OPERATION)

    def test_history_is_bounded_and_immutable(self):
        contracts = self.m.empty()
        for index in range(200):
            contracts = contracts.observe(
                host_event("suspended" if index % 2 else "active", index + 1))
        self.assertLessEqual(len(contracts.history), self.m.MAX_HISTORY)
        with self.assertRaises(Exception):
            contracts.history.append("x")
        view = contracts.view()
        self.assertEqual(view["phase"], contracts.phase)
        with self.assertRaises(TypeError):
            view["phase"] = "active"
        self.assertEqual(contracts.to_dict()["phase"], contracts.phase)

    def test_source_is_pure_no_real_host_effects(self):
        root = Path(self.m.__file__).resolve().parent.parent.parent
        source = (root / "canopy_features" / "reliability"
                  / "suspend_resume_contracts.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "dbus", "QTimer",
                          "time.sleep", "socket", "vbox"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
