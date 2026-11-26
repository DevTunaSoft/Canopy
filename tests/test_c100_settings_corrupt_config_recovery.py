"""Targeted RED/GREEN tests for Classic preference corrupt-config recovery.

These are host-side source-contract tests only. They use bounded temporary
directories, synthetic marker strings instead of real credentials, and never
assert compiled Qt, Mint or visual behavior.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from canopy_features.accessibility import reduced_motion_contract as motion
import canopy_features.settings.persisted_preferences as source
from canopy_features.settings import (
    PersistedPreferences,
    PersistedPreferencesError,
)

# Synthetic marker only. It is not a credential and must never appear in a
# log record, an exception message or a diagnostic string.
MARKER = "SYNTHETIC_PE009_MARKER_7B41"


class CorruptConfigRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "state" / "preferences.json"
        self.path.parent.mkdir(parents=True)
        self.sidecar = Path(str(self.path) + ".corrupt")

    def _corrupt_bytes(self, marker=MARKER):
        return (b'{"version":1,"values":{"reduced_motion":"reduce"},'
                b'"note":"' + marker.encode("ascii") + b'"}\x00')

    def test_corrupt_config_loads_defaults_and_keeps_raw_bytes_on_recovery(self):
        raw = self._corrupt_bytes()
        self.path.write_bytes(raw)
        store = PersistedPreferences(self.path)
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)
        self.assertTrue(store.set("reduced_motion", motion.FULL))
        self.assertTrue(self.sidecar.exists())
        self.assertEqual(self.sidecar.read_bytes(), raw)
        self.assertEqual(
            PersistedPreferences(self.path).view("reduced_motion").value,
            motion.FULL,
        )

    def test_valid_config_survives_restart_without_quarantine_or_rewrite(self):
        raw = json.dumps(
            {"version": 1, "values": {"reduced_motion": motion.REDUCE}}
        ).encode("utf-8")
        self.path.write_bytes(raw)
        store = PersistedPreferences(self.path)
        self.assertEqual(store.view("reduced_motion").value, motion.REDUCE)
        self.assertEqual(
            PersistedPreferences(self.path).view("reduced_motion").value,
            motion.REDUCE,
        )
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertFalse(self.sidecar.exists())

    def test_partly_valid_config_falls_back_safely_and_quarantines_raw_bytes(self):
        # Established contract: any invalid field discards the whole document
        # for the in-memory view, but the raw bytes must survive recovery.
        raw = json.dumps({
            "version": 1,
            "values": {"reduced_motion": motion.REDUCE, "power": "suspend"},
        }).encode("utf-8")
        self.path.write_bytes(raw)
        store = PersistedPreferences(self.path)
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)
        self.assertTrue(store.set("reduced_motion", motion.FULL))
        self.assertEqual(self.sidecar.read_bytes(), raw)
        self.assertEqual(
            PersistedPreferences(self.path).view("reduced_motion").value,
            motion.FULL,
        )

    def test_recovery_writes_no_log_records_containing_config_bytes(self):
        self.path.write_bytes(self._corrupt_bytes())
        store = PersistedPreferences(self.path)
        with self.assertNoLogs(level="DEBUG"):
            self.assertTrue(store.set("reduced_motion", motion.FULL))
        self.assertIn(MARKER, self.sidecar.read_text(errors="replace"))

    def test_recovery_leaves_no_temporary_files(self):
        self.path.write_bytes(self._corrupt_bytes())
        store = PersistedPreferences(self.path)
        store.set("reduced_motion", motion.FULL)
        leftovers = sorted(name for name in os.listdir(self.path.parent)
                           if name.startswith(".canopy-prefs-"))
        self.assertEqual(leftovers, [])

    def test_oversized_config_is_bounded_read_and_never_overwritten(self):
        raw = MARKER.encode("ascii") + b" " * (source.MAX_STATE_BYTES * 8)
        self.path.write_bytes(raw)
        with mock.patch("pathlib.Path.read_bytes",
                        side_effect=AssertionError("unbounded read")):
            store = PersistedPreferences(self.path)
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)
        with self.assertRaises(PersistedPreferencesError) as raised:
            store.set("reduced_motion", motion.FULL)
        self.assertNotIn(MARKER, str(raised.exception))
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertFalse(self.sidecar.exists())

    def test_quarantine_rotation_is_bounded(self):
        first = self._corrupt_bytes("PE009_FIRST")
        self.path.write_bytes(first)
        store = PersistedPreferences(self.path)
        store.set("reduced_motion", motion.FULL)
        second = self._corrupt_bytes("PE009_SECOND")
        self.path.write_bytes(second)
        PersistedPreferences(self.path).set("reduced_motion", motion.REDUCE)
        self.assertEqual(self.sidecar.read_bytes(), second)
        self.assertEqual(
            Path(str(self.path) + ".corrupt.1").read_bytes(), first)
        copies = sorted(name for name in os.listdir(self.path.parent)
                        if ".corrupt" in name)
        self.assertLessEqual(len(copies), 3)
        for name in copies:
            self.assertLessEqual((self.path.parent / name).stat().st_size,
                                 source.MAX_STATE_BYTES)

    def test_symlinked_quarantine_target_is_refused_without_data_loss(self):
        root = self.root / "users" / "alice"
        root.mkdir(parents=True)
        state = root / "preferences.json"
        state.write_bytes(self._corrupt_bytes())
        target = root / "other.json"
        target.write_bytes(b"other-profile-data")
        alias = Path(str(state) + ".corrupt")
        try:
            alias.symlink_to(target)
        except (OSError, NotImplementedError, ValueError) as exc:
            self.skipTest("symlinks unavailable on this host: %s" % exc)
        store = PersistedPreferences(state, root=self.root)
        with self.assertRaises(PersistedPreferencesError):
            store.set("reduced_motion", motion.FULL)
        self.assertEqual(state.read_bytes(), self._corrupt_bytes())
        self.assertEqual(target.read_bytes(), b"other-profile-data")


if __name__ == "__main__":
    unittest.main()
