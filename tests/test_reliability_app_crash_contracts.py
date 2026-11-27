"""Source-contract tests for application crash handling.

Every signal in these tests travels through the existing
``canopy_core.host_events`` bus. The production module never launches,
signals or kills a process.
"""
import ast
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from canopy_core.host_events import (
    TOPICS as HOST_EVENT_TOPICS,
    HostEvents,
)

from canopy_features.reliability.app_crash_contracts import (
    STATUS_ISOLATED,
    CLEANABLE_RESOURCES,
    CrashContractError,
    TrustedCrashEventSource,
)

APP = "org.example.Mail.desktop"


class DetectionTests(unittest.TestCase):
    def test_real_window_event_detects_crash_and_isolates_app(self):
        source = TrustedCrashEventSource()
        try:
            result = source.emit("window.state.changed", {
                "state": "crashed", "app_id": APP, "pid": 4242,
                "exit_code": 3,
            })
            self.assertEqual((result.delivered, result.callback_failures),
                             (1, 0))
            self.assertTrue(source.controller.is_isolated(APP))
            snapshot = source.snapshot()
            self.assertEqual(snapshot.crash_count, 1)
            self.assertEqual(snapshot.status, STATUS_ISOLATED)
        finally:
            source.close()


class DetectionFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.source = TrustedCrashEventSource()

    def tearDown(self):
        self.source.close()

    def test_clean_exit_does_not_isolate_another_app(self):
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP, "pid": 42, "exit_code": 3})
        self.source.emit("window.state.changed", {
            "state": "exited", "app_id": "org.example.Other.desktop",
            "pid": 43, "exit_code": 0})
        self.assertTrue(self.source.controller.is_isolated(APP))
        self.assertFalse(self.source.controller.is_isolated(
            "org.example.Other.desktop"))
        self.assertEqual(self.source.snapshot().crash_count, 1)

    def test_unknown_window_state_creates_no_crash_claim(self):
        self.source.emit("window.state.changed", {
            "state": "alive", "app_id": APP, "pid": 42, "exit_code": 3})
        self.assertFalse(self.source.controller.is_isolated(APP))
        self.assertEqual(self.source.snapshot().crash_count, 0)

    def test_replayed_event_sequence_is_stale(self):
        result = self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP, "pid": 42, "exit_code": 3})
        self.assertEqual(
            self.source.controller.observe(result.event), "STALE")
        self.assertEqual(self.source.snapshot().crash_count, 1)

    def test_tracked_app_capacity_fails_closed(self):
        from canopy_features.reliability.app_crash_contracts import (
            MAX_TRACKED_APPS)

        for index in range(MAX_TRACKED_APPS + 1):
            self.source.emit("window.state.changed", {
                "state": "crashed",
                "app_id": "org.example.App%02d.desktop" % index,
                "pid": index + 1, "exit_code": 3})
        self.assertEqual(self.source.snapshot().crash_count,
                         MAX_TRACKED_APPS)
        self.assertFalse(self.source.controller.is_isolated(
            "org.example.App%02d.desktop" % MAX_TRACKED_APPS))


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.source = TrustedCrashEventSource()
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP, "pid": 42, "exit_code": 3})

    def tearDown(self):
        self.source.close()

    def test_cleanup_is_bounded_and_idempotent(self):
        controller = self.source.controller
        resources = ("window", "notification", "cache", "subscription",
                     "shortcut", "badge", "focus", "timer")
        first = controller.cleanup(APP, resources)
        self.assertEqual((first.released, first.remaining, first.done),
                         (4, 4, False))
        second = controller.cleanup(APP, resources)
        self.assertEqual((second.released, second.remaining, second.done),
                         (4, 0, True))
        third = controller.cleanup(APP, resources)
        self.assertEqual((third.released, third.remaining, third.done),
                         (0, 0, True))
        self.assertEqual(self.source.snapshot().cleanup_count, 8)

    def test_cleanup_is_denied_for_a_non_isolated_app(self):
        result = self.source.controller.cleanup(
            "org.example.Other.desktop", ("window",))
        self.assertEqual(result.status, "DENIED")
        self.assertEqual((result.released, result.remaining), (0, 1))

    def test_unknown_resource_changes_nothing(self):
        with self.assertRaises(CrashContractError):
            self.source.controller.cleanup(APP, ("window", "kill-process"))
        self.assertEqual(self.source.snapshot().cleanup_count, 0)

    def test_cleanup_after_close_fails_closed(self):
        controller = self.source.controller
        self.source.close()
        with self.assertRaises(CrashContractError):
            controller.cleanup(APP, ("window",))


class RecoveryAndFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.source = TrustedCrashEventSource()
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP, "pid": 42, "exit_code": 3})

    def tearDown(self):
        self.source.close()

    def test_feedback_is_stable_and_never_echoes_source_text(self):
        first = self.source.controller.feedback(APP)
        second = self.source.controller.feedback(APP)
        self.assertEqual(first, second)
        self.assertEqual(first.code, "APP_ISOLATED")
        self.assertNotIn(APP, first.message)
        self.assertNotIn("42", first.message)
        self.assertNotIn("3", first.message)

    def test_recovery_requires_a_cleanup_done_session_event(self):
        controller = self.source.controller
        resources = ("window", "notification", "cache", "subscription",
                     "shortcut", "badge", "focus", "timer")
        controller.cleanup(APP, resources)
        self.assertEqual(
            self.source.emit("session.state.changed", {
                "state": "active", "phase": "recovery_granted",
                "app_id": APP}).delivered, 1)
        self.assertEqual(controller.feedback(APP).code, "APP_ISOLATED")
        controller.cleanup(APP, resources)
        self.source.emit("session.state.changed", {
            "state": "active", "phase": "recovery_granted", "app_id": APP})
        self.assertEqual(controller.feedback(APP).code, "APP_RECOVERABLE")

    def test_recovery_event_without_cleanup_is_ignored(self):
        self.source.emit("session.state.changed", {
            "state": "active", "phase": "recovery_granted", "app_id": APP})
        self.assertEqual(self.source.controller.feedback(APP).code,
                         "APP_ISOLATED")

    def test_acknowledge_clears_isolation_and_returns_ready(self):
        controller = self.source.controller
        resources = ("window", "notification", "cache", "subscription",
                     "shortcut", "badge", "focus", "timer")
        controller.cleanup(APP, resources)
        controller.cleanup(APP, resources)
        self.source.emit("session.state.changed", {
            "state": "active", "phase": "recovery_granted", "app_id": APP})
        self.assertTrue(controller.acknowledge(APP))
        self.assertFalse(controller.is_isolated(APP))
        self.assertEqual(controller.feedback(APP).code, "READY")
        self.assertEqual(self.source.snapshot().recovery_count, 1)

    def test_recovery_count_is_bounded(self):
        from canopy_features.reliability.app_crash_contracts import (
            MAX_RECOVERIES)

        resources = ("window", "notification", "cache", "subscription",
                     "shortcut", "badge", "focus", "timer")
        for index in range(MAX_RECOVERIES):
            app = "org.example.Rec%03d.desktop" % index
            self.source.emit("window.state.changed", {
                "state": "crashed", "app_id": app, "pid": index + 1,
                "exit_code": 3})
            self.source.controller.cleanup(app, resources)
            self.source.controller.cleanup(app, resources)
            self.source.emit("session.state.changed", {
                "state": "active", "phase": "recovery_granted", "app_id": app})
            self.assertTrue(self.source.controller.acknowledge(app))
        app = "org.example.Overflow.desktop"
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": app, "pid": 9000, "exit_code": 3})
        self.source.controller.cleanup(app, resources)
        self.source.controller.cleanup(app, resources)
        self.source.emit("session.state.changed", {
            "state": "active", "phase": "recovery_granted", "app_id": app})
        self.assertEqual(self.source.controller.feedback(app).code,
                         "APP_ISOLATED")
        self.assertEqual(self.source.snapshot().recovery_count,
                         MAX_RECOVERIES)

    def test_feedback_after_close_is_unavailable(self):
        controller = self.source.controller
        self.source.close()
        self.assertEqual(controller.feedback(APP).code, "STATE_UNAVAILABLE")
        self.assertFalse(controller.acknowledge(APP))

    def test_hostile_app_id_gets_unavailable_feedback(self):
        self.assertEqual(
            self.source.controller.feedback(object()).code,
            "STATE_UNAVAILABLE")


class HostileInputTests(unittest.TestCase):
    def setUp(self):
        self.source = TrustedCrashEventSource()

    def tearDown(self):
        self.source.close()

    def test_control_character_app_id_creates_no_crash_claim(self):
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP + "\ninjected",
            "pid": 42, "exit_code": 3})
        self.assertEqual(self.source.snapshot().crash_count, 0)

    def test_boolean_pid_is_not_a_crash_signal(self):
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP, "pid": True, "exit_code": 3})
        self.assertFalse(self.source.controller.is_isolated(APP))

    def test_non_tuple_cleanup_input_fails_closed(self):
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP, "pid": 42, "exit_code": 3})
        with self.assertRaises(CrashContractError):
            self.source.controller.cleanup(APP, ["window"])
        with self.assertRaises(CrashContractError):
            self.source.controller.cleanup(
                APP, ("window",) * (len(CLEANABLE_RESOURCES) + 1))

    def test_only_real_host_events_are_accepted(self):
        with self.assertRaises(CrashContractError):
            self.source.controller.observe(object())

    def test_unallowed_topic_is_rejected_by_controller(self):
        bus = HostEvents({})
        result = bus.emit("capabilities.report", {"status": "CAPABILITY_REPORT"})
        with self.assertRaises(CrashContractError):
            self.source.controller.observe(result.event)

    def test_snapshot_is_no_echo_and_frozen(self):
        self.source.emit("window.state.changed", {
            "state": "crashed", "app_id": APP, "pid": 4242, "exit_code": 3})
        snapshot = self.source.snapshot()
        payload = repr(snapshot.to_dict())
        for value in (APP, "4242", "window.state.changed"):
            self.assertNotIn(value, payload)
        with self.assertRaises(FrozenInstanceError):
            snapshot.crash_count = 9

    def test_close_is_idempotent_and_fails_closed(self):
        self.source.close()
        self.source.close()
        with self.assertRaises(CrashContractError):
            self.source.emit("window.state.changed", {
                "state": "crashed", "app_id": APP, "pid": 42, "exit_code": 3})


class ContractAlignmentTests(unittest.TestCase):
    def test_allowed_topics_are_existing_host_event_topics_only(self):
        from canopy_features.reliability.app_crash_contracts import (
            ALLOWED_TOPICS)

        self.assertTrue(set(ALLOWED_TOPICS).issubset(HOST_EVENT_TOPICS))
        self.assertEqual(len(ALLOWED_TOPICS), 2)
        self.assertNotIn("capabilities.report", ALLOWED_TOPICS)

    def test_module_declares_no_process_or_io_import(self):
        from canopy_features.reliability import app_crash_contracts as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.issubset(
            {"dataclasses", "types", "re", "canopy_core"}), imported)
        source = Path(module.__file__).read_text(encoding="utf-8")
        for token in ("subprocess", "Popen", "os.kill", "socket", "open("):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class SyntheticChildTests(unittest.TestCase):
    def test_bounded_synthetic_child_exit_drives_one_crash_contract(self):
        # The only child in this suite exits by itself. No signal or kill is
        # sent to any process; the contract module never sees the child.
        completed = subprocess.run(
            [sys.executable, "-c", "import sys; sys.exit(7)"],
            capture_output=True, timeout=5, check=False)
        self.assertEqual(completed.returncode, 7)
        source = TrustedCrashEventSource()
        try:
            source.emit("window.state.changed", {
                "state": "exited", "app_id": APP, "pid": 4242,
                "exit_code": completed.returncode})
            self.assertTrue(source.controller.is_isolated(APP))
            snapshot = source.snapshot()
            self.assertEqual(snapshot.crash_count, 1)
            self.assertEqual(snapshot.process_action, "NOT_PERFORMED")
        finally:
            source.close()


if __name__ == "__main__":
    unittest.main()
