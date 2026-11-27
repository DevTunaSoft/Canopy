"""Targeted, offline tests for the bounded native suspend/resume host path.

No real suspend, resume, login, D-Bus, VM, Qt, compiled UI, thread, timer or
poll loop is exercised. Every event is constructed in-process from the existing
protocol v2 host event primitive.
"""
import unittest

from canopy_core.host_events import HostEvent
from canopy_features.reliability.lock_session_events import SessionState
from canopy_features.reliability.suspend_resume_contracts import (
    OPERATIONS, REASON_RESUME_PENDING, REASON_SUSPENDED, REASON_UNKNOWN)
from canopy_features.reliability.suspend_resume_native import (
    MAX_DRAIN, MAX_PENDING, REASON_CLOSED, REASON_HOST_UNAVAILABLE,
    REASON_INVALID_OPERATION, SuspendResumeNativeError,
    SuspendResumeNativePath)


def host_event(state, sequence=1):
    """Build a delivered host event using only the existing v2 primitive."""
    return HostEvent(2, "session.state.changed", sequence, (("state", state),))


class NativePathDefaultTests(unittest.TestCase):
    def setUp(self):
        self.path = SuspendResumeNativePath()

    def test_unknown_default_denies_every_operation(self):
        self.assertEqual(self.path.availability, "UNAVAILABLE")
        for operation in OPERATIONS:
            decision = self.path.decide(operation)
            self.assertFalse(decision.available)
            self.assertEqual(decision.reason, REASON_UNKNOWN)
            self.assertTrue(decision.disclosure)

    def test_invalid_operation_denies_with_stable_reason(self):
        for operation in (None, 7, "reboot", b"launch_app", ["read_status"]):
            decision = self.path.decide(operation)
            self.assertFalse(decision.available)
            self.assertEqual(decision.reason, REASON_INVALID_OPERATION)

    def test_exact_host_event_type_topic_version_and_sequence_required(self):
        bad = (
            ("not an event",),
            (HostEvent(2, "window.state.changed", 1, (("state", "active"),)),),
            (HostEvent(1, "session.state.changed", 1, (("state", "active"),)),),
            (HostEvent(2, "session.state.changed", -1, (("state", "active"),)),),
            (HostEvent(2, "session.state.changed", "1", (("state", "active"),)),),
        )
        for (event,) in bad:
            with self.subTest(event=event):
                with self.assertRaises(SuspendResumeNativeError):
                    self.path.submit(event)

    def test_forged_host_event_subclass_is_rejected(self):
        class Forged(HostEvent):
            @property
            def payload(self):
                class Fake:
                    @staticmethod
                    def get(key):
                        return "active"
                return Fake()

        with self.assertRaises(SuspendResumeNativeError):
            self.path.submit(Forged(2, "session.state.changed", 1, ()))

    def test_constructor_bounds_fail_closed(self):
        for kwargs in ({"max_pending": 0}, {"max_pending": MAX_PENDING + 1},
                       {"max_pending": True}, {"max_drain": MAX_DRAIN + 1},
                       {"max_drain": 1.5}, {"overflow_policy": "anything"},
                       {"overflow_policy": ["reject_new"]}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SuspendResumeNativeError):
                    SuspendResumeNativePath(**kwargs)


class IntakeBoundTests(unittest.TestCase):
    def test_pending_queue_is_bounded_and_overflow_fails_closed(self):
        path = SuspendResumeNativePath()
        for sequence in range(1, MAX_PENDING + 1):
            result = path.submit(host_event("active", sequence))
            self.assertTrue(result.accepted)
        overflow = path.submit(host_event("suspended", MAX_PENDING + 1))
        self.assertFalse(overflow.accepted)
        self.assertEqual(path.view()["boundary"], "unavailable")
        self.assertEqual(path.view()["pending"], 0)
        self.assertEqual(path.decide("launch_app").reason,
                         REASON_HOST_UNAVAILABLE)
        with self.assertRaises(SuspendResumeNativeError):
            path.submit(host_event("active", MAX_PENDING + 2))
        with self.assertRaises(SuspendResumeNativeError):
            path.drain()

    def test_drop_oldest_overflow_also_fails_closed(self):
        path = SuspendResumeNativePath(overflow_policy="drop_oldest")
        for sequence in range(1, MAX_PENDING + 1):
            path.submit(host_event("active", sequence))
        result = path.submit(host_event("suspended", MAX_PENDING + 1))
        self.assertTrue(result.accepted)
        self.assertEqual(path.stats["dropped"], 1)
        self.assertEqual(path.decide("read_status").reason,
                         REASON_HOST_UNAVAILABLE)

    def test_submit_many_consumes_at_most_max_pending(self):
        # A finite, counting generator: an unbounded implementation would read
        # all 100 items and the assertion would fail. The generator is finite
        # so a regression cannot hang the test run.
        seen = []

        def events():
            for sequence in range(1, 101):
                seen.append(sequence)
                yield host_event("active", sequence)

        path = SuspendResumeNativePath()
        result = path.submit_many(events())
        self.assertEqual(len(seen), MAX_PENDING)
        self.assertEqual(result.consumed, MAX_PENDING)
        self.assertEqual(result.queued, MAX_PENDING)
        self.assertEqual(result.rejected, 0)
        self.assertFalse(result.stopped)

    def test_submit_many_rejects_scalar_and_mapping_inputs(self):
        path = SuspendResumeNativePath()
        for batch in ("active", b"active", {"state": "active"}, 7, None):
            with self.subTest(batch=batch):
                with self.assertRaises(SuspendResumeNativeError):
                    path.submit_many(batch)

    def test_drain_limit_is_bounded(self):
        path = SuspendResumeNativePath(max_pending=8, max_drain=4)
        for sequence in range(1, 9):
            path.submit(host_event("suspended", sequence))
        self.assertEqual(path.drain().processed, 4)
        self.assertEqual(path.view()["pending"], 4)
        for bad in (0, MAX_DRAIN + 1, True, 1.5, "4"):
            with self.assertRaises(SuspendResumeNativeError):
                path.drain(limit=bad)


class DecisionFlowTests(unittest.TestCase):
    def test_suspended_event_denies_every_operation(self):
        path = SuspendResumeNativePath()
        path.submit(host_event("suspended"))
        report = path.drain()
        self.assertEqual(report.phase, "suspended")
        self.assertEqual(path.decide("focus_window").reason, REASON_SUSPENDED)
        for operation in OPERATIONS:
            self.assertFalse(path.decide(operation).available)

    def test_resume_requires_explicit_reobservation(self):
        path = SuspendResumeNativePath()
        path.submit(host_event("suspended", 1))
        path.drain()
        path.submit(host_event("active", 2))
        path.drain()
        self.assertEqual(path.view()["phase"], "resume_pending")
        self.assertEqual(path.decide("launch_app").reason,
                         REASON_RESUME_PENDING)
        path.resume_ready()
        self.assertTrue(path.decide("launch_app").available)

    def test_resume_ready_rejects_without_observed_resume(self):
        path = SuspendResumeNativePath()
        for event in (None, host_event("suspended")):
            if event is not None:
                path.submit(event)
                path.drain()
            with self.assertRaises(SuspendResumeNativeError):
                path.resume_ready()

    def test_stale_event_cannot_regress_a_fail_closed_phase(self):
        path = SuspendResumeNativePath()
        path.submit(host_event("suspended", 5))
        path.drain()
        path.submit(host_event("active", 4))
        report = path.drain()
        self.assertEqual(report.ignored, 1)
        self.assertEqual(path.view()["phase"], "suspended")
        self.assertFalse(path.decide("launch_app").available)

    def test_malformed_state_degrades_to_unknown_without_raising(self):
        for state in (None, 7, "sleeping", "SUSPENDED"):
            path = SuspendResumeNativePath()
            path.submit(host_event(state))
            path.drain()
            self.assertEqual(path.view()["phase"], "unknown")
            self.assertFalse(path.decide("launch_app").available)

    def test_session_state_path_reads_durable_flags_only(self):
        path = SuspendResumeNativePath()
        path.observe_session_state(SessionState(suspended=True, locked=True))
        self.assertEqual(path.decide("launch_app").reason, REASON_SUSPENDED)
        for forged in (None, {"suspended": True, "locked": True},
                       type("Fake", (), {"suspended": True, "locked": True})()):
            with self.assertRaises(SuspendResumeNativeError):
                path.observe_session_state(forged)


class BoundaryLossTests(unittest.TestCase):
    def _activated(self):
        path = SuspendResumeNativePath()
        path.submit(host_event("active", 1))
        path.drain()
        self.assertTrue(path.decide("launch_app").available)
        return path

    def test_host_unavailable_clears_active_and_denies(self):
        path = self._activated()
        path.mark_host_unavailable()
        self.assertEqual(path.decide("launch_app").reason,
                         REASON_HOST_UNAVAILABLE)
        self.assertEqual(path.view()["phase"], "unknown")
        self.assertEqual(path.view()["pending"], 0)
        self.assertTrue(path.view()["reobservation_required"])

    def test_recovery_requires_fresh_observation_and_acknowledgment(self):
        path = self._activated()
        path.mark_host_unavailable()
        self.assertTrue(path.mark_host_available())
        self.assertFalse(path.mark_host_available())
        self.assertFalse(path.decide("launch_app").available)
        # A stale pre-loss event cannot re-enable anything.
        path.submit(host_event("active", 1))
        path.drain()
        self.assertFalse(path.decide("launch_app").available)
        # A fresh active observation is necessary but not sufficient.
        path.submit(host_event("active", 2))
        path.drain()
        self.assertEqual(path.decide("launch_app").reason,
                         REASON_RESUME_PENDING)
        path.resume_ready()
        self.assertTrue(path.decide("launch_app").available)

    def test_close_is_irreversible_and_denies(self):
        path = self._activated()
        path.close()
        path.close()
        self.assertEqual(path.decide("launch_app").reason, REASON_CLOSED)
        for action in (lambda: path.submit(host_event("active", 9)),
                       path.drain, lambda: path.observe_session_state(
                           SessionState(False, False)),
                       path.resume_ready, path.mark_host_available,
                       path.mark_host_unavailable):
            with self.assertRaises(SuspendResumeNativeError):
                action()

    def test_view_is_read_only_bounded_and_discloses_no_payload(self):
        path = SuspendResumeNativePath()
        path.submit(host_event("suspended", 1))
        path.drain()
        snapshot = path.view()
        with self.assertRaises(TypeError):
            snapshot["phase"] = "active"
        self.assertEqual(snapshot["counts"]["submitted"], 1)
        self.assertEqual(path.to_dict()["phase"], "suspended")
        self.assertEqual(snapshot["disclosure"],
                         "Unavailable — host is suspended")
        self.assertLessEqual(len(snapshot["history"]), 32)

    def test_no_payload_string_reaches_a_disclosure(self):
        path = SuspendResumeNativePath()
        event = HostEvent(2, "session.state.changed", 1,
                          (("state", "active"), ("note", "s3cr3t-payload")))
        path.submit(event)
        path.drain()
        for operation in OPERATIONS:
            self.assertNotIn("s3cr3t", path.decide(operation).disclosure)
        self.assertNotIn("s3cr3t", str(path.to_dict()))


if __name__ == "__main__":
    unittest.main()
