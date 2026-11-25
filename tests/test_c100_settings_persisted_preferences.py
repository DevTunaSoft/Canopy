"""Contract tests for the fail-closed Classic settings panel."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import canopy_core.host_events as host_events
from canopy_core.host_events import TOPICS
from canopy_features.accessibility import reduced_motion_contract as motion
import canopy_features.settings.persisted_preferences as preferences_source
from canopy_features.system import quick_controls_state as quick
from canopy_features.settings import (
    KEYS,
    PersistedPreferences,
    PersistedPreferencesError,
    view_for_key,
)


class PersistedPreferencesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "state" / "preferences.json"

    def test_default_view_is_fail_closed_and_grounded(self):
        view = view_for_key("reduced_motion")
        self.assertTrue(view.available)
        self.assertEqual(view.value, motion.UNSET)
        self.assertIn("reduced_motion_contract", view.source)
        self.assertIn("visuals do not change", view.disclosure)

    def test_each_domain_has_a_visible_unavailable_disclosure(self):
        for key in ("network", "audio", "power", "session"):
            with self.subTest(key=key):
                view = view_for_key(key)
                self.assertFalse(view.available)
                self.assertTrue(view.disclosure.startswith("Unavailable — "))
                self.assertEqual(view.source,
                                 "canopy_features.system.quick_controls_state")
        for key in ("power", "session"):
            self.assertIn("privileged", view_for_key(key).disclosure)

    def test_unavailable_keys_use_existing_contract_text(self):
        self.assertEqual(view_for_key("network").disclosure,
                         quick.DISCLOSURES[quick.REASON_NO_HOST_INTERFACE])
        self.assertEqual(view_for_key("power").disclosure,
                         quick.DISCLOSURES[quick.REASON_PRIVILEGED_HOST_CHANGE])

    def test_no_new_host_event_topic(self):
        # Exact approved identity: no new topic, and no duplicate standing in
        # for an omitted approved one.
        self.assertEqual(len(TOPICS), 4)
        self.assertNotIn("settings.changed", TOPICS)
        self.assertEqual(len(set(TOPICS)), len(TOPICS))
        self.assertEqual(set(TOPICS), preferences_source.HOST_EVENT_TOPICS)

    def test_only_reduced_motion_is_writable(self):
        self.assertEqual(
            {key for key, definition in KEYS.items() if definition["available"]},
            {"reduced_motion"},
        )

    def test_round_trip_persists_valid_value(self):
        store = PersistedPreferences(self.path)
        self.assertTrue(store.set("reduced_motion", motion.REDUCE))
        self.assertEqual(store.view("reduced_motion").value, motion.REDUCE)
        reloaded = PersistedPreferences(self.path)
        self.assertEqual(reloaded.view("reduced_motion").value, motion.REDUCE)
        self.assertIn("version", self.path.read_text())

    def test_invalid_value_does_not_change_state(self):
        store = PersistedPreferences(self.path)
        with self.assertRaises(PersistedPreferencesError):
            store.set("reduced_motion", "fast")
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)
        self.assertFalse(self.path.exists())

    def test_unavailable_key_refuses_write(self):
        store = PersistedPreferences(self.path)
        self.assertFalse(store.set("power", "suspend"))
        self.assertFalse(self.path.exists())
        self.assertEqual(store.view("power").value, "")

    def test_wrong_types_fail_closed(self):
        store = PersistedPreferences(self.path)
        for key in (None, 7, b"reduced_motion", ["reduced_motion"], {"a": 1}):
            with self.subTest(key=key):
                with self.assertRaises(PersistedPreferencesError):
                    store.view(key)
        for value in (None, 1, True, ["reduce"], {"v": "reduce"}):
            with self.subTest(value=value):
                with self.assertRaises(PersistedPreferencesError):
                    store.set("reduced_motion", value)

    def test_unknown_key_fails_closed(self):
        store = PersistedPreferences(self.path)
        with self.assertRaises(PersistedPreferencesError):
            store.view("secret_admin_override")
        with self.assertRaises(PersistedPreferencesError):
            store.set("secret_admin_override", "on")

    def test_corrupt_state_starts_empty(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        store = PersistedPreferences(self.path)
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)

    def test_duplicate_keys_are_rejected(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            '{"version":1,"values":{"reduced_motion":"reduce"},'
            '"values":{"reduced_motion":"full"}}'
        )
        store = PersistedPreferences(self.path)
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)

    def test_unknown_and_unavailable_persisted_keys_are_discarded(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "version": 1,
            "values": {"reduced_motion": "reduce", "power": "suspend"},
        }))
        store = PersistedPreferences(self.path)
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)

    def test_bad_schema_version_and_constants_rejected(self):
        self.path.parent.mkdir(parents=True)
        for document in (
            {"version": True, "values": {}},
            {"version": 2, "values": {}},
            {"version": 1.5, "values": {}},
        ):
            with self.subTest(document=document):
                self.path.write_text(json.dumps(document))
                self.assertEqual(
                    PersistedPreferences(self.path).view("reduced_motion").value,
                    motion.UNSET,
                )
        self.path.write_text(
            '{"version":1,"values":{"reduced_motion":NaN}}')
        self.assertEqual(
            PersistedPreferences(self.path).view("reduced_motion").value,
            motion.UNSET,
        )

    def test_oversized_state_is_discarded(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(" " * 5000)
        self.assertEqual(
            PersistedPreferences(self.path).view("reduced_motion").value,
            motion.UNSET,
        )

    def test_snapshot_is_immutable_and_complete(self):
        store = PersistedPreferences(self.path)
        snapshot = store.snapshot()
        self.assertEqual(set(snapshot), set(KEYS))
        with self.assertRaises(TypeError):
            snapshot["reduced_motion"] = None

    def test_no_default_privileged_path(self):
        with self.assertRaises(PersistedPreferencesError):
            PersistedPreferences(b"/etc/canopy/settings.json")
        with self.assertRaises(PersistedPreferencesError):
            PersistedPreferences(7)

    def test_atomic_write_leaves_no_temporary_files(self):
        store = PersistedPreferences(self.path)
        store.set("reduced_motion", motion.FULL)
        leftovers = [name for name in os.listdir(self.path.parent)
                     if name.startswith(".canopy-prefs-")]
        self.assertEqual(leftovers, [])


class HostEventTopicSourceContractTests(unittest.TestCase):
    """Negative controls for the settings panel's host-topic source contract.

    A length check plus a single membership check is not an exact-set claim:
    duplicating one approved topic while omitting another keeps the entry
    count and still contains no private settings topic. These controls feed
    exactly that shape to the settings module's import-time source gate and
    require it to fail closed.
    """

    APPROVED_TOPICS = (
        "app.catalog.changed",
        "window.state.changed",
        "session.state.changed",
        "capabilities.report",
    )

    def _load_with_topics(self, topics):
        """Import a fresh settings module against a crafted topic source."""
        spec = importlib.util.spec_from_file_location(
            "_settings_topic_contract_probe", preferences_source.__file__)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(host_events, "TOPICS", topics):
            spec.loader.exec_module(module)
        return module

    def _topic_gate(self):
        gate = getattr(preferences_source, "checked_host_event_topics", None)
        self.assertIsNotNone(
            gate, "settings source contract must expose a topic-set gate")
        return gate

    def test_duplicate_topic_with_one_omitted_is_rejected_on_load(self):
        # Four entries, capabilities.report present and no "settings.changed":
        # both old checks pass even though session.state.changed is omitted.
        crafted = ("app.catalog.changed", "window.state.changed",
                   "window.state.changed", "capabilities.report")
        with self.assertRaises(RuntimeError):
            self._load_with_topics(crafted)

    def test_unapproved_extra_topic_with_one_omitted_is_rejected_on_load(self):
        # Same length, capabilities.report present, no "settings.changed",
        # but session.state.changed was replaced by a private-looking topic.
        crafted = ("app.catalog.changed", "window.state.changed",
                   "capabilities.report", "capabilities.extra")
        with self.assertRaises(RuntimeError):
            self._load_with_topics(crafted)

    def test_duplicate_appended_to_approved_set_is_rejected_on_load(self):
        crafted = self.APPROVED_TOPICS + ("capabilities.report",)
        with self.assertRaises(RuntimeError):
            self._load_with_topics(crafted)

    def test_topic_gate_rejects_duplicate_with_one_omitted(self):
        crafted = ("app.catalog.changed", "window.state.changed",
                   "window.state.changed", "capabilities.report")
        with self.assertRaises(PersistedPreferencesError):
            self._topic_gate()(crafted)

    def test_topic_gate_rejects_unapproved_extra_topic(self):
        crafted = ("app.catalog.changed", "window.state.changed",
                   "capabilities.report", "capabilities.extra")
        with self.assertRaises(PersistedPreferencesError):
            self._topic_gate()(crafted)

    def test_topic_gate_accepts_only_the_approved_set(self):
        gate = self._topic_gate()
        self.assertEqual(gate(self.APPROVED_TOPICS),
                         frozenset(self.APPROVED_TOPICS))
        for crafted in (("app.catalog.changed",), None, "capabilities.report",
                        [1, 2, 3, 4]):
            with self.subTest(crafted=crafted):
                with self.assertRaises(PersistedPreferencesError):
                    gate(crafted)

    def test_topic_guard_performs_no_privileged_writes(self):
        crafted = ("app.catalog.changed", "window.state.changed",
                   "window.state.changed", "capabilities.report")
        with mock.patch("pathlib.Path.write_bytes") as write_bytes, \
                mock.patch("pathlib.Path.mkdir") as mkdir, \
                mock.patch("os.replace") as replace, \
                mock.patch("os.chmod") as chmod:
            with self.assertRaises(RuntimeError):
                self._load_with_topics(crafted)
            self.assertFalse(write_bytes.called)
            self.assertFalse(mkdir.called)
            self.assertFalse(replace.called)
            self.assertFalse(chmod.called)


if __name__ == "__main__":
    unittest.main()
