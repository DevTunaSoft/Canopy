"""Fail-closed tests for the pure trusted hostActivationSnapshot producer.

These tests are SYNTHETIC Python-only checks. They never compile Qt, inject a
record into the compiled host, observe a window manager or claim a running
desktop. Host injection is a later serialized step requiring main.cpp
ownership and is NOT_RUN here.
"""
import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType
from unittest.mock import patch

from canopy_features.apps import window_activation_producer as producer
from canopy_features.windows import focus_intents as focus
from canopy_features.windows import switcher_state as switcher
from canopy_features.windows import workspace_inventory as inventory

SOURCE = Path(producer.__file__)

# Exact required key set of WindowActivationState::applySnapshot in the
# compiled state component (mirrored literally, not read from another PR).
CPP_REQUIRED_KEYS = frozenset({
    "schema", "backend", "negotiation", "sequence", "installed",
    "owners", "grants", "launcherEnabled",
})


def _inventory():
    return inventory.build_inventory(
        [{"source": "test", "name": "Alpha", "identifier": "alpha"},
         {"source": "test", "name": "Beta", "identifier": "beta"}],
        permitted_sources=frozenset({"test"}))


def _focus(grant=True):
    policy = focus.PermissionPolicy()
    if grant:
        policy.grant("shell", "files")
    broker = focus.FocusBroker(policy.authorize)
    ref = broker.register_window("files", 10)
    broker.request_focus(focus.FocusIntent("shell", ref))
    return broker, policy


def _focus_activation_failed():
    policy = focus.PermissionPolicy()
    policy.grant("shell", "files")
    broker = focus.FocusBroker(policy.authorize, activate=lambda *_: False)
    ref = broker.register_window("files", 10)
    broker.request_focus(focus.FocusIntent("shell", ref))
    return broker, policy


def _switcher():
    state = switcher.SwitcherState([10, 20, 30], current=10)
    state.begin()
    state.next()
    return state.snapshot()


def _compose(**overrides):
    broker, policy = _focus()
    kwargs = dict(backend="x11", sequence=7, launcher_enabled=True,
                  installed=("Files", "Mail"))
    kwargs.update(overrides)
    return producer.compose(_inventory(), broker, _switcher(),
                            policy=policy, **kwargs)


class TrustedSchemaTests(unittest.TestCase):
    def test_emits_exact_trusted_host_schema(self):
        record = _compose()
        view = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertEqual(tuple(view), producer.HOST_KEYS)
        self.assertEqual(frozenset(view), CPP_REQUIRED_KEYS)
        self.assertIs(type(view["schema"]), int)
        self.assertEqual(view["schema"], 1)
        self.assertIs(type(view["sequence"]), int)
        self.assertEqual(view["sequence"], 7)
        self.assertIs(type(view["backend"]), str)
        self.assertEqual(view["backend"], "x11")
        self.assertIs(type(view["negotiation"]), str)
        self.assertIs(type(view["launcherEnabled"]), bool)
        self.assertEqual(view["installed"], ("Mail", "Files"))
        self.assertEqual(view["owners"], ())
        self.assertEqual(view["grants"], ())
        self.assertNotIn("focus", view)

    def test_negotiation_mirrors_known_backend(self):
        for backend, expected in (("x11", "SUPPORTED"),
                                  ("wayland", "SUPPORTED"),
                                  ("headless", "PARTIAL")):
            with self.subTest(backend=backend):
                self.assertEqual(_compose(backend=backend).negotiation, expected)
        # No trusted input can emit UNSUPPORTED: an unknown backend is refused.
        self.assertNotEqual(_compose().negotiation, "UNSUPPORTED")

    def test_installed_is_canonical_ordered_and_deduplicated(self):
        record = _compose(installed=("Mail", "Files"))
        self.assertEqual(record.installed, ("Mail", "Files"))
        single = _compose(installed=("Settings",))
        self.assertEqual(single.installed, ("Settings",))

    def test_no_process_window_or_permission_telemetry_invented(self):
        payload = json.loads(_compose().to_json_bytes().decode("utf-8"))
        self.assertEqual(payload["owners"], [])
        self.assertEqual(payload["grants"], [])
        self.assertNotIn("focus", payload)
        self.assertEqual(frozenset(payload), CPP_REQUIRED_KEYS)

    def test_record_frozen_and_view_fresh_read_only(self):
        record = _compose()
        with self.assertRaises(FrozenInstanceError):
            record.status = "tampered"
        view = record.to_dict()
        again = record.to_dict()
        self.assertIsNot(view, again)
        with self.assertRaises(TypeError):
            view["launcherEnabled"] = False
        with self.assertRaises(TypeError):
            view["installed"] = ()

    def test_json_bytes_are_deterministic_and_array_shaped(self):
        first = _compose().to_json_bytes()
        second = _compose().to_json_bytes()
        self.assertEqual(first, second)
        payload = json.loads(first.decode("utf-8"))
        for key in ("installed", "owners", "grants"):
            self.assertIs(type(payload[key]), list)
        self.assertIn(b'"launcherEnabled":true', first)

    def test_blocked_focus_decision_is_not_republished(self):
        broker, policy = _focus(grant=False)
        with self.assertRaises(producer.ProducerError):
            producer.compose(_inventory(), broker, _switcher(),
                             backend="x11", sequence=1, launcher_enabled=True,
                             installed=("Files",), policy=policy)

    def test_activation_failed_decision_is_not_republished(self):
        broker, policy = _focus_activation_failed()
        with self.assertRaises(producer.ProducerError):
            producer.compose(_inventory(), broker, _switcher(),
                             backend="x11", sequence=1, launcher_enabled=True,
                             installed=("Files",), policy=policy)


class HostileInputTests(unittest.TestCase):
    def test_backend_fail_closed(self):
        for bad in (None, 1, True, [], {}, (), "", "wayland-evil", "X11",
                    "x" * 129, bytearray(b"x11")):
            with self.subTest(bad=repr(bad)), self.assertRaises(producer.ProducerError):
                _compose(backend=bad)

    def test_sequence_fail_closed(self):
        for bad in (True, False, -1, 1.0, "1", None, [], {}, 2**31, -(2**31)):
            with self.subTest(bad=repr(bad)), self.assertRaises(producer.ProducerError):
                _compose(sequence=bad)

    def test_launcher_enabled_fail_closed(self):
        for bad in (1, 0, 1.0, "true", None, [], {}):
            with self.subTest(bad=repr(bad)), self.assertRaises(producer.ProducerError):
                _compose(launcher_enabled=bad)

    def test_installed_container_fail_closed(self):
        # Generators and sets are refused: an unordered or lazy source cannot
        # define the host's bounded, ordered install set.
        for bad in ("Files", b"Files", bytearray(b"Files"), {"Files"},
                    frozenset({"Files"}), {"Files": True}, None, 1,
                    (name for name in ("Files",))):
            with self.subTest(bad=repr(bad)), self.assertRaises(producer.ProducerError):
                _compose(installed=bad)

    def test_installed_member_fail_closed(self):
        for bad in ((None,), (1,), (True,), ("files",), ("Evil",),
                    ("F" * 129,), ([],), ({},), (b"Files",)):
            with self.subTest(bad=repr(bad)), self.assertRaises(producer.ProducerError):
                _compose(installed=bad)

    def test_installed_bounds_and_duplicates_fail_closed(self):
        for bad in (tuple("Files" for _ in range(65)), ("Files", "Files")):
            with self.subTest(size=len(bad)), self.assertRaises(producer.ProducerError):
                _compose(installed=bad)

    def test_hostile_contract_objects_fail_closed(self):
        broker, policy = _focus()
        cases = (
            (None, broker, _switcher(), policy),
            ({}, broker, _switcher(), policy),
            ("workspace", broker, _switcher(), policy),
            (_inventory(), None, _switcher(), policy),
            (_inventory(), {}, _switcher(), policy),
            (_inventory(), broker, None, policy),
            (_inventory(), broker, [], policy),
            (_inventory(), broker, _switcher(), "policy"),
        )
        for workspace, focus_broker, switcher_state, pol in cases:
            with self.subTest(workspace=type(workspace).__name__,
                              focus=type(focus_broker).__name__,
                              switcher=type(switcher_state).__name__,
                              policy=type(pol).__name__):
                with self.assertRaises(producer.ProducerError):
                    producer.compose(workspace, focus_broker, switcher_state,
                                     backend="x11", sequence=1,
                                     launcher_enabled=True,
                                     installed=("Files",), policy=pol)

    def test_unhashable_values_do_not_leak_builtin_errors(self):
        # The bug class is a raw TypeError escaping before the domain error.
        with self.assertRaises(producer.ProducerError):
            _compose(backend=["x11"])
        with self.assertRaises(producer.ProducerError):
            _compose(installed=[{"Files"}])


class PurityTests(unittest.TestCase):
    def test_no_io_process_qt_or_clock_imports(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        forbidden = {"os", "sys", "subprocess", "socket", "pathlib", "time",
                     "datetime", "random", "threading", "multiprocessing",
                     "PyQt5", "PySide6"}
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertFalse(found & forbidden, "unexpected imports: %r" % (found & forbidden))

    def test_compose_and_serialize_open_no_files(self):
        with patch("builtins.open", side_effect=AssertionError("file I/O attempted")):
            record = _compose()
            record.to_json_bytes()
        self.assertEqual(record.backend, "x11")


if __name__ == "__main__":
    unittest.main()
