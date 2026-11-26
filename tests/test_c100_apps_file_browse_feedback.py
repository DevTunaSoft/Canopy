"""Targeted contract tests for PE-064 file/folder browse failure feedback.

Pure Python only: no Qt runtime, no filesystem mutation, no process launch.
The reason-code vocabulary mirrors ``native_file_open`` (PE-016, PR #666, not
present at this base tip); the transport reuses an existing v2 host event
topic and its existing ``state`` field without extending the host contract.
"""
import unittest
from dataclasses import FrozenInstanceError

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
    HostEvents,
)
from canopy_features.apps import file_browse_feedback as module
from canopy_features.apps.file_browse_feedback import (
    DENIED,
    FEEDBACK,
    FEEDBACK_FIELD,
    FEEDBACK_TOPIC,
    FIXED_CLAIMS,
    REASON_CANCELLED,
    REASON_EMPTY_PATH,
    REASON_HANDLER_MISSING,
    REASON_HANDLER_UNAVAILABLE,
    REASON_HOME_UNAVAILABLE,
    REASON_INVALID_PATH,
    REASON_MISSING_TARGET,
    REASON_NO_DEFAULT_APP,
    REASON_OK,
    REASON_OPEN_FAILED,
    REASON_OUTSIDE_HOME,
    REASON_PERMISSION_DENIED,
    REASON_TOO_LONG,
    REASON_UNKNOWN,
    REASON_UNSUPPORTED_TYPE,
    BrowseFeedback,
    BrowseFeedbackError,
    browse_failure,
    failure_event_payload,
    failure_feedback,
    from_host_event,
)


class _HostileStr(str):
    def __eq__(self, other):
        return True

    def __hash__(self):
        return 42


class BrowseFeedbackVocabularyTests(unittest.TestCase):
    def test_reason_codes_are_fixed_and_cover_all_browse_failures(self):
        expected = {
            REASON_OK, REASON_HOME_UNAVAILABLE, REASON_INVALID_PATH,
            REASON_EMPTY_PATH, REASON_TOO_LONG, REASON_MISSING_TARGET,
            REASON_UNSUPPORTED_TYPE, REASON_OUTSIDE_HOME,
            REASON_HANDLER_UNAVAILABLE, REASON_PERMISSION_DENIED,
            REASON_HANDLER_MISSING, REASON_NO_DEFAULT_APP, REASON_OPEN_FAILED,
            REASON_CANCELLED, REASON_UNKNOWN,
        }
        self.assertEqual(len(expected), 15)
        for code in expected:
            self.assertIs(type(code), str)
            self.assertRegex(code, r"\A[a-z][a-z0-9_]{0,47}\Z")
        self.assertEqual(REASON_PERMISSION_DENIED, "permission_denied")
        self.assertEqual(REASON_INVALID_PATH, "invalid_path")

    def test_permission_denied_feedback_is_fixed_and_path_free(self):
        message = failure_feedback(REASON_PERMISSION_DENIED)
        self.assertEqual(message, "Permission was denied; nothing was opened.")
        self.assertNotIn("/", message)
        self.assertNotIn("\\", message)

    def test_every_malformed_path_code_has_a_distinct_fixed_message(self):
        codes = (
            REASON_INVALID_PATH, REASON_EMPTY_PATH, REASON_TOO_LONG,
            REASON_MISSING_TARGET, REASON_UNSUPPORTED_TYPE, REASON_OUTSIDE_HOME,
            REASON_HOME_UNAVAILABLE,
        )
        messages = tuple(failure_feedback(code) for code in codes)
        self.assertEqual(len(set(messages)), len(codes))
        for code, message in zip(codes, messages):
            self.assertIs(type(message), str)
            self.assertEqual(message, FEEDBACK[code])
            for marker in ("/", "\\", "notes.txt", "c:\\users"):
                self.assertNotIn(marker, message.lower())

    def test_failure_feedback_fails_closed_for_hostile_reason_types(self):
        valid = set(FEEDBACK.values())
        for hostile in (None, 42, b"permission_denied", [], {}, _HostileStr("permission_denied")):
            with self.subTest(hostile=type(hostile).__name__):
                message = failure_feedback(hostile)
                self.assertIs(type(message), str)
                self.assertNotIn(message, valid)
                self.assertNotIn("permission_denied", message)

    def test_unknown_reason_gets_the_fixed_unrecognized_message(self):
        message = failure_feedback("notes/private.txt")
        self.assertEqual(message, "The system reported an unrecognized open failure.")
        self.assertNotIn("notes", message)


class BrowseFailureRecordTests(unittest.TestCase):
    def test_browse_failure_is_denied_immutable_and_path_free(self):
        record = browse_failure(REASON_PERMISSION_DENIED)
        self.assertEqual(record.status, DENIED)
        self.assertEqual(record.reason, REASON_PERMISSION_DENIED)
        self.assertEqual(record.feedback, FEEDBACK[REASON_PERMISSION_DENIED])
        self.assertEqual(record.claims, FIXED_CLAIMS)
        self.assertFalse(record.approved)
        with self.assertRaises(FrozenInstanceError):
            setattr(record, "reason", REASON_OK)

    def test_browse_failure_bridge_is_fresh_and_carries_no_path_field(self):
        record = browse_failure(REASON_INVALID_PATH)
        first = record.to_dict()
        second = record.to_dict()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first), {"status", "reason", "feedback", "claims"})
        self.assertNotIn("path", first)
        self.assertNotIn("target", first)
        first["reason"] = "forged"
        self.assertEqual(record.reason, REASON_INVALID_PATH)

    def test_every_failure_reason_yields_a_denied_record(self):
        for code in FEEDBACK:
            if code == REASON_OK:
                continue
            with self.subTest(code=code):
                self.assertFalse(browse_failure(code).approved)

    def test_success_reason_cannot_be_reported_as_a_failure(self):
        with self.assertRaises(BrowseFeedbackError):
            browse_failure(REASON_OK)

    def test_direct_record_construction_is_fail_closed(self):
        with self.assertRaises(BrowseFeedbackError):
            BrowseFeedback(DENIED, REASON_PERMISSION_DENIED, "forged message")
        with self.assertRaises(BrowseFeedbackError):
            BrowseFeedback(DENIED, _HostileStr(REASON_PERMISSION_DENIED),
                           FEEDBACK[REASON_PERMISSION_DENIED])


class HostEventFeedbackContractTests(unittest.TestCase):
    def test_topic_and_field_reuse_the_existing_host_event_contract(self):
        self.assertEqual(PROTOCOL_VERSION, 2)
        self.assertEqual(len(HOST_EVENT_TOPICS), 4)
        self.assertIn(FEEDBACK_TOPIC, HOST_EVENT_TOPICS)
        self.assertEqual(FEEDBACK_FIELD, "state")

    def test_failure_payload_uses_only_the_existing_state_field(self):
        payload = failure_event_payload(REASON_PERMISSION_DENIED)
        self.assertEqual(payload, {"state": REASON_PERMISSION_DENIED})
        self.assertEqual(set(payload), {FEEDBACK_FIELD})

    def test_failure_payload_refuses_untrusted_reason_values(self):
        for hostile in (None, "notes/private.txt", _HostileStr(REASON_INVALID_PATH), [], 3):
            with self.subTest(hostile=type(hostile).__name__):
                with self.assertRaises(BrowseFeedbackError):
                    failure_event_payload(hostile)

    def _deliver(self, payload):
        seen = []
        callback = seen.append
        bus = HostEvents({FEEDBACK_TOPIC: [callback]})
        token = bus.subscribe(FEEDBACK_TOPIC, callback)
        result = bus.emit(FEEDBACK_TOPIC, payload)
        bus.unsubscribe(token)
        bus.close()
        self.assertEqual(result.delivered, 1)
        self.assertEqual(result.callback_failures, 0)
        self.assertEqual(len(seen), 1)
        return result.event

    def test_real_permission_event_round_trip_yields_fixed_feedback(self):
        event = self._deliver(failure_event_payload(REASON_PERMISSION_DENIED))
        self.assertIs(type(event), HostEvent)
        record = from_host_event(event)
        self.assertEqual(record.reason, REASON_PERMISSION_DENIED)
        self.assertEqual(record.feedback, failure_feedback(REASON_PERMISSION_DENIED))
        self.assertEqual(record.status, DENIED)

    def test_real_malformed_path_event_round_trip_yields_fixed_feedback(self):
        event = self._deliver(failure_event_payload(REASON_INVALID_PATH))
        record = from_host_event(event)
        self.assertEqual(record.reason, REASON_INVALID_PATH)
        self.assertEqual(record.feedback, failure_feedback(REASON_INVALID_PATH))

    def test_foreign_or_wrong_envelope_events_are_refused(self):
        good = self._deliver(failure_event_payload(REASON_PERMISSION_DENIED))
        malformed = (
            {"state": REASON_PERMISSION_DENIED},
            object(),
            HostEvent(good.version, "app.catalog.changed", good.sequence,
                      ((FEEDBACK_FIELD, REASON_PERMISSION_DENIED),)),
            HostEvent(1, good.topic, good.sequence,
                      ((FEEDBACK_FIELD, REASON_PERMISSION_DENIED),)),
        )
        for candidate in malformed:
            with self.subTest(candidate=type(candidate).__name__):
                with self.assertRaises(BrowseFeedbackError):
                    from_host_event(candidate)

    def test_missing_or_hostile_state_fails_closed_without_echo(self):
        for payload in ({"available": True}, {"state": "notes/private.txt"},
                        {"state": _HostileStr(REASON_PERMISSION_DENIED)}):
            with self.subTest(payload=sorted(payload)):
                if any(type(value) is _HostileStr for value in payload.values()):
                    # The real bus refuses str subclasses at emit; construct
                    # the envelope directly to exercise the adapter's own gate.
                    event = HostEvent(PROTOCOL_VERSION, FEEDBACK_TOPIC, 1,
                                      tuple(sorted(payload.items())))
                else:
                    event = self._deliver(payload)
                record = from_host_event(event)
                self.assertEqual(record.reason, REASON_UNKNOWN)
                self.assertEqual(record.feedback, failure_feedback(REASON_UNKNOWN))
                self.assertNotIn("notes", record.feedback)

    def test_module_source_has_no_io_or_process_launch_api(self):
        source = (module.__file__ and __import__("pathlib").Path(
            module.__file__).read_text(encoding="utf-8"))
        for forbidden in ("subprocess", "os.system", "shell=True", "Popen",
                          "QProcess", "socket", "open(", "write_text",
                          "unlink(", "shutil", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
