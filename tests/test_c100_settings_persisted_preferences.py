"""Contract tests for the fail-closed Classic settings panel."""

import json
import os
from pathlib import Path
import tempfile
import unittest

from canopy_core.host_events import TOPICS
from canopy_features.accessibility import reduced_motion_contract as motion
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
        # The settings contract must not invent a private event topic.
        self.assertEqual(len(TOPICS), 4)
        self.assertNotIn("settings.changed", TOPICS)

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


if __name__ == "__main__":
    unittest.main()
