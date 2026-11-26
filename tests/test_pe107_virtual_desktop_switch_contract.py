"""PE-107 contract tests for read-only virtual desktop switch requests.

The recorder is an in-process adapter over the existing host-event bus. All
authorizing events in these tests are real ``HostEvent`` objects emitted by
that bus; no fabricated event is ever accepted as a request trigger.
"""
import ast
import unittest
from pathlib import Path
from types import MappingProxyType

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEventError,
)

from canopy_features.windows.virtual_desktop_switch_contract import (
    ACCEPTANCE_NOT_ESTABLISHED,
    ALLOWED_TOPICS,
    DIRECTIONS,
    KIND_DIRECTION,
    KIND_IDENTIFIER,
    KIND_INDEX,
    MAX_REQUESTS,
    MAX_WORKSPACES,
    OBSERVATION_NOT_PERFORMED,
    POLLING_ENABLED,
    REASON_DUPLICATE,
    REASON_RECORDED,
    SCHEMA,
    SOURCE,
    STATUS_IGNORED,
    STATUS_RECORDED,
    WM_REQUESTS,
    SwitchRequestError,
    VirtualDesktopSwitchRecorder,
)

ROOT = Path(__file__).resolve().parents[1]


class RecorderContractTests(unittest.TestCase):
    def setUp(self):
        self.recorder = VirtualDesktopSwitchRecorder()

    def tearDown(self):
        self.recorder.close()

    def test_real_host_event_records_one_read_only_switch_request(self):
        result = self.recorder.emit("session.state.changed", {"state": "active"})
        record = self.recorder.request(
            result.event, kind=KIND_IDENTIFIER, target="workspace-2", label="Dev")
        self.assertEqual(record.status, STATUS_RECORDED)
        self.assertEqual(record.reason, REASON_RECORDED)
        self.assertEqual(record.schema, SCHEMA)
        self.assertEqual(record.source, SOURCE)
        self.assertEqual(record.topic, "session.state.changed")
        self.assertEqual(record.sequence, result.event.sequence)
        self.assertEqual(record.kind, KIND_IDENTIFIER)
        self.assertEqual(record.target, "workspace-2")
        self.assertEqual(record.label, "Dev")
        self.assertEqual(record.acceptance, ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.observation, OBSERVATION_NOT_PERFORMED)
        self.assertEqual(record.wm_requests, WM_REQUESTS)
        self.assertIs(record.polling, POLLING_ENABLED)
        snapshot = self.recorder.snapshot()
        self.assertEqual(len(snapshot), 1)
        self.assertIsInstance(snapshot[0], MappingProxyType)
        self.assertEqual(dict(snapshot[0]), record.to_dict())

    def test_index_and_direction_targets_are_recorded(self):
        first = self.recorder.emit("window.state.changed", {"window_count": 2})
        second = self.recorder.emit("app.catalog.changed", {"item_count": 4})
        index = self.recorder.request(first.event, kind=KIND_INDEX, target=3)
        direction = self.recorder.request(second.event, kind=KIND_DIRECTION,
                                          target="next")
        self.assertEqual((index.kind, index.target), (KIND_INDEX, 3))
        self.assertEqual((direction.kind, direction.target),
                         (KIND_DIRECTION, "next"))
        self.assertEqual(direction.label, "")
        self.assertEqual(len(self.recorder.snapshot()), 2)

    def test_snapshot_is_bounded_and_newest_first(self):
        for index in range(MAX_REQUESTS + 2):
            result = self.recorder.emit("app.catalog.changed",
                                        {"item_count": index})
            self.recorder.request(result.event, kind=KIND_INDEX,
                                  target=index + 1)
        snapshot = self.recorder.snapshot()
        self.assertEqual(len(snapshot), MAX_REQUESTS)
        sequences = [row["sequence"] for row in snapshot]
        self.assertEqual(sequences,
                         list(range(MAX_REQUESTS + 2, 2, -1)))
        self.assertEqual([row["target"] for row in snapshot],
                         list(range(MAX_REQUESTS + 2, 2, -1)))

    def test_duplicate_request_is_ignored_without_snapshot_growth(self):
        result = self.recorder.emit("session.state.changed", {"state": "active"})
        first = self.recorder.request(result.event, kind=KIND_INDEX, target=1)
        second = self.recorder.request(result.event, kind=KIND_INDEX, target=1)
        self.assertEqual(first.status, STATUS_RECORDED)
        self.assertEqual(second.status, STATUS_IGNORED)
        self.assertEqual(second.reason, REASON_DUPLICATE)
        self.assertEqual(self.recorder.ignored_count, 1)
        self.assertEqual(len(self.recorder.snapshot()), 1)

    def test_same_event_can_record_distinct_targets(self):
        result = self.recorder.emit("session.state.changed", {"state": "active"})
        self.recorder.request(result.event, kind=KIND_INDEX, target=1)
        self.recorder.request(result.event, kind=KIND_INDEX, target=2)
        self.assertEqual([row["target"] for row in self.recorder.snapshot()],
                         [2, 1])

    def test_snapshot_records_are_read_only_copies(self):
        result = self.recorder.emit("session.state.changed", {"state": "active"})
        self.recorder.request(result.event, kind=KIND_INDEX, target=1)
        with self.assertRaises(TypeError):
            self.recorder.snapshot()[0]["target"] = 99
        self.assertEqual(self.recorder.snapshot()[0]["target"], 1)

    def test_close_fails_closed_and_clears_records(self):
        result = self.recorder.emit("session.state.changed", {"state": "active"})
        self.recorder.request(result.event, kind=KIND_INDEX, target=1)
        self.recorder.close()
        self.recorder.close()
        self.assertFalse(self.recorder.connected())
        self.assertEqual(self.recorder.snapshot(), ())
        with self.assertRaises(SwitchRequestError):
            self.recorder.emit("session.state.changed", {"state": "active"})
        with self.assertRaises(SwitchRequestError):
            self.recorder.request(result.event, kind=KIND_INDEX, target=2)

    def test_event_from_another_bus_cannot_authorize_a_request(self):
        other = VirtualDesktopSwitchRecorder()
        try:
            result = other.emit("session.state.changed", {"state": "active"})
            with self.assertRaises(SwitchRequestError):
                self.recorder.request(result.event, kind=KIND_INDEX, target=1)
            self.assertEqual(self.recorder.snapshot(), ())
        finally:
            other.close()

    def test_stale_event_after_bound_overflow_cannot_authorize_a_request(self):
        first = self.recorder.emit("session.state.changed", {"state": "active"})
        for index in range(MAX_REQUESTS):
            self.recorder.emit("app.catalog.changed", {"item_count": index})
        with self.assertRaises(SwitchRequestError):
            self.recorder.request(first.event, kind=KIND_INDEX, target=1)
        self.assertEqual(self.recorder.snapshot(), ())

    def test_request_does_not_change_the_event_payload(self):
        result = self.recorder.emit("session.state.changed", {"state": "active"})
        self.recorder.request(result.event, kind=KIND_INDEX, target=1)
        self.assertEqual(dict(result.event.payload), {"state": "active"})
        self.assertNotIn("workspace", dict(result.event.payload))
        keys = set(self.recorder.snapshot()[0])
        self.assertNotIn("payload", keys)
        self.assertNotIn("callback", keys)


class HostileInputTests(unittest.TestCase):
    def setUp(self):
        self.recorder = VirtualDesktopSwitchRecorder()
        self.result = self.recorder.emit("session.state.changed",
                                         {"state": "active"})

    def tearDown(self):
        self.recorder.close()

    def test_non_event_objects_are_rejected(self):
        for event in (object(), {"topic": "session.state.changed"}, None, True):
            with self.subTest(event=event):
                with self.assertRaises(SwitchRequestError):
                    self.recorder.request(event, kind=KIND_INDEX, target=1)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(SwitchRequestError):
            self.recorder.request(self.result.event, kind="desktop", target=1)

    def test_index_rejects_bool_float_zero_and_out_of_range(self):
        for target in (True, False, 1.0, 0, -1, MAX_WORKSPACES + 1, "3", None):
            with self.subTest(target=target):
                with self.assertRaises(SwitchRequestError):
                    self.recorder.request(self.result.event, kind=KIND_INDEX,
                                          target=target)

    def test_identifier_rejects_control_and_nonprintable_text(self):
        for target in ("", "workspace\n1", "\u202eworkspace", "\ud800",
                       "x" * 65, 12):
            with self.subTest(target=target):
                with self.assertRaises(SwitchRequestError):
                    self.recorder.request(self.result.event,
                                          kind=KIND_IDENTIFIER, target=target)

    def test_direction_accepts_only_fixed_tokens(self):
        for token in DIRECTIONS:
            with self.subTest(token=token):
                record = self.recorder.request(self.result.event,
                                               kind=KIND_DIRECTION,
                                               target=token)
                self.assertEqual(record.target, token)
        for token in ("sideways", "NEXT", "", 3):
            with self.subTest(token=token):
                with self.assertRaises(SwitchRequestError):
                    self.recorder.request(self.result.event,
                                          kind=KIND_DIRECTION, target=token)

    def test_label_is_bounded_and_safe(self):
        for label in ("x" * 121, "bad\u202elabel", "line\nbreak", "\ud800", 7):
            with self.subTest(label=label):
                with self.assertRaises(SwitchRequestError):
                    self.recorder.request(self.result.event, kind=KIND_INDEX,
                                          target=1, label=label)

    def test_invalid_capacity_is_rejected(self):
        for capacity in (0, -1, MAX_REQUESTS + 1, True, 2.0, "4", None):
            with self.subTest(capacity=capacity):
                with self.assertRaises(SwitchRequestError):
                    VirtualDesktopSwitchRecorder(max_requests=capacity)

    def test_no_new_topic_or_protocol_version_is_accepted(self):
        self.assertEqual(ALLOWED_TOPICS, tuple(sorted(HOST_EVENT_TOPICS)))
        self.assertEqual(len(ALLOWED_TOPICS), 4)
        self.assertEqual(PROTOCOL_VERSION, 2)
        with self.assertRaises(HostEventError):
            self.recorder.emit("virtual.desktop.switch", {"target": "workspace-2"})

    def test_rejected_emits_leave_no_request(self):
        with self.assertRaises(HostEventError):
            self.recorder.emit("session.state.changed", {"workspace": "x" * 600})
        self.assertEqual(self.recorder.snapshot(), ())


class ContractBoundaryTests(unittest.TestCase):
    def test_host_event_topics_are_exactly_the_documented_four(self):
        self.assertEqual(ALLOWED_TOPICS, tuple(sorted(HOST_EVENT_TOPICS)))
        self.assertEqual(set(ALLOWED_TOPICS), {
            "app.catalog.changed", "window.state.changed",
            "session.state.changed", "capabilities.report"})

    def test_module_imports_no_execution_ui_or_sibling_contract(self):
        path = ROOT / "canopy_features" / "windows" / \
            "virtual_desktop_switch_contract.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0]
                                for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.issubset({"collections", "dataclasses",
                                           "types", "unicodedata",
                                           "canopy_core"}), imported)
        for forbidden in ("subprocess", "socket", "threading", "asyncio",
                          "PySide6", "PyQt5", "dbus"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, imported)

    def test_module_does_not_construct_host_events(self):
        path = ROOT / "canopy_features" / "windows" / \
            "virtual_desktop_switch_contract.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        for call in calls:
            name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
            self.assertNotEqual(name, "HostEvent")

    def test_documented_contract_pins_the_read_only_boundary(self):
        doc = (ROOT / "docs" / "VIRTUAL_DESKTOP_SWITCH_CONTRACT.md").read_text(
            encoding="utf-8")
        for token in ("no new host-event topic", "WM_REQUESTS = 0",
                      "NOT_ESTABLISHED", "NOT_PERFORMED",
                      "serialized switch request", "PE-086", "PE-102"):
            with self.subTest(token=token):
                self.assertIn(token, doc)


if __name__ == "__main__":
    unittest.main()
