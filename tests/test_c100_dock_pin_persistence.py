"""Targeted regression tests for durable Classic dock pin order (PE-004).

Offline source-contract tests only: no Qt, no VM, no full suite, no visual
assets. A fresh ``DockPinStore`` over the same path models an application
restart and proves that pinned order survives it.
"""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from canopy_features.dock import dock_pinned_items as pins
from canopy_features.dock import dock_pin_persistence as persistence


class PinPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="canopy-pe004-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = persistence.state_path_for_user(self.root, "alice")
        self.store = persistence.DockPinStore(self.path, root=self.root)

    def _reopen(self, path=None, root=None):
        return persistence.DockPinStore(path or self.path, root=root or self.root)

    def test_absent_state_is_empty_and_loading_writes_nothing(self):
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.snapshot(), ())
        self.assertEqual(self.store.status, "ABSENT")
        self.assertFalse(self.path.exists())

    def test_pin_order_survives_a_restart(self):
        self.store.pin("nemo")
        self.store.pin("terminal")
        self.store.pin("files")
        self.assertEqual(self.store.snapshot(), ("nemo", "terminal", "files"))
        self.store.move("terminal", 0)
        expected = ("terminal", "nemo", "files")
        self.assertEqual(self.store.snapshot(), expected)
        restarted = self._reopen()
        self.assertEqual(restarted.snapshot(), expected)
        self.assertEqual(restarted.status, "OK")
        restarted.pin("browser")
        self.assertEqual(self._reopen().snapshot(),
                         expected + ("browser",))

    def test_unpin_and_repin_persist_without_duplicates(self):
        self.store.pin("nemo")
        self.store.pin("terminal")
        self.store.unpin("nemo")
        self.assertEqual(self._reopen().snapshot(), ("terminal",))
        self.store.unpin("missing")
        self.assertEqual(self._reopen().snapshot(), ("terminal",))
        self.store.pin("terminal")
        self.store.pin("nemo")
        self.assertEqual(self._reopen().snapshot(), ("terminal", "nemo"))

    def test_each_profile_keeps_its_own_pinned_order(self):
        alice = persistence.DockPinStore.for_user(self.root, "alice")
        bob = persistence.DockPinStore.for_user(self.root, "bob")
        alice.pin("nemo")
        bob.pin("browser")
        bob.pin("files")
        self.assertEqual(alice.snapshot(), ("nemo",))
        self.assertEqual(bob.snapshot(), ("browser", "files"))
        self.assertEqual(
            persistence.DockPinStore.for_user(self.root, "alice").snapshot(),
            ("nemo",))
        self.assertNotEqual(alice.path, bob.path)

    def _corrupt_samples(self):
        return (
            b"{not json",
            b"[]",
            b'{"version":1,"items":["nemo","nemo"]}',
            b'{"version":2,"items":["nemo"]}',
            b'{"version":true,"items":["nemo"]}',
            b'{"version":NaN,"items":[]}',
            b'{"version":1,"items":"nemo"}',
            b'{"version":1,"items":[7]}',
            b'{"version":1,"items":[" nemo "]}',
            b'{"version":1,"items":["nemo"],"extra":1}',
            b'{"version":1,"items":["nemo"],"items":["browser"]}',
            b'{"version":1,"items":["\\ud800"]}',
            b'{"version":1,"items":["nemo"]}\xff',
            b'{"version":1,"items":["' + b"x" * 5000 + b'"]}',
        )

    def test_corrupt_state_is_discarded_without_mutating_the_file(self):
        for number, raw in enumerate(self._corrupt_samples()):
            with self.subTest(corrupt=raw[:40]):
                case_root = self.root / f"case-{number}"
                case_root.mkdir()
                path = persistence.state_path_for_user(case_root, "alice")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                store = persistence.DockPinStore(path, root=case_root)
                self.assertEqual(store.snapshot(), ())
                self.assertEqual(store.status, "CORRUPT")
                self.assertEqual(path.read_bytes(), raw)
                # Recovery is a clean, ordered rewrite on the next user action.
                store.pin("nemo")
                self.assertEqual(store.snapshot(), ("nemo",))
                self.assertEqual(self._reopen(path, case_root).snapshot(),
                                 ("nemo",))

    def test_failed_write_rolls_back_memory_and_keeps_file_absent(self):
        with mock.patch.object(persistence.os, "replace",
                               side_effect=OSError("injected write failure")):
            with self.assertRaises(persistence.DockPinPersistenceError):
                self.store.pin("nemo")
        self.assertEqual(self.store.snapshot(), ())
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.glob(".canopy-dock-pins-*")), [])

    def test_hostile_pin_inputs_never_write(self):
        for app_id in ("", " nemo ", "x" * (pins.MAX_ID_LENGTH + 1),
                       7, None, b"x", "\ud800"):
            with self.subTest(app_id=app_id):
                with self.assertRaises(ValueError):
                    self.store.pin(app_id)
        for call in (lambda: self.store.unpin([]),
                     lambda: self.store.pin(True),
                     lambda: self.store.move("nemo", True)):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(self.store.snapshot(), ())
        self.assertFalse(self.path.exists())

    def test_invalid_profile_and_path_boundaries_are_refused(self):
        for user in ("", "ALICE", "../bob", "a/b", None, 7):
            with self.subTest(user=user):
                with self.assertRaises(persistence.DockPinPersistenceError):
                    persistence.state_path_for_user(self.root, user)
        with self.assertRaises(persistence.DockPinPersistenceError):
            persistence.DockPinStore(self.path)  # root is mandatory
        outside = self.root.parent / "outside-dock-pins.json"
        with self.assertRaises(persistence.DockPinPersistenceError):
            persistence.DockPinStore(outside, root=self.root)
        with self.assertRaises(persistence.DockPinPersistenceError):
            persistence.DockPinStore(self.root / ".." / "escape.json",
                                     root=self.root)

    @unittest.skipIf(os.name == "nt",
                     "POSIX mode bits are not authoritative on Windows")
    def test_state_file_is_private_and_no_temporary_files_remain(self):
        self.store.pin("nemo")
        mode = stat.S_IMODE(self.path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(list(self.root.glob("users/alice/.canopy-dock-pins-*")),
                         [])
        self.assertEqual(
            {p.name for p in self.root.rglob("*") if p.is_file()},
            {"dock_pins.json"})

    def test_source_contract_has_no_ui_or_runtime_dependencies(self):
        source = inspect.getsource(persistence)
        for token in ("PyQt", "PySide", "QML", "subprocess", "socket",
                      "threading", "QProcess", "while True"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        self.assertEqual(persistence.FORMAT_VERSION, 1)
        self.assertEqual(persistence.STATE_BASENAME, "dock_pins.json")
        self.assertEqual(pins.MAX_PINS, 64)
        # Canonical bytes are deterministic and carry no host-specific path.
        self.store.pin("nemo")
        self.assertEqual(
            self.path.read_bytes(),
            b'{"items":["nemo"],"version":1}',
        )
        self.assertEqual(json.loads(self.path.read_bytes())["items"], ["nemo"])


if __name__ == "__main__":
    unittest.main()
