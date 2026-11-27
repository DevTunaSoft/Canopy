"""Synthetic contract tests for the native daemon interop boundary.

Every case is a deterministic in-process probe. No D-Bus, daemon, socket,
desktop notification, process, timer, poll, thread, filesystem access or VM is
used. Positive cases use the existing trusted host source; negative cases use
finite hostile callers and mappings.
"""
import ast
import dataclasses
from collections.abc import Mapping
import unittest
from pathlib import Path

from canopy_features.notifications.daemon_interop import (
    AVAILABLE,
    AVAILABLE_KEY,
    CAPABILITY_ABSENT,
    CAPABILITY_KEY,
    CAPABILITY_PRESENT,
    CAPABILITY_REFUSED,
    CLOSED,
    DaemonInteropError,
    INTEROP_CLOSED,
    INVALID_CAPABILITY,
    INVALID_SOURCE,
    MAX_PROBES,
    NATIVE_INTEROP,
    NONE,
    NOT_PROBED,
    NO_SOURCE,
    PROBE_LIMIT,
    SOURCE_LIVE,
    SOURCE_LOST,
    UNAVAILABLE,
    NotificationDaemonInterop,
)
from canopy_features.notifications.host_event_source import TrustedHostEventSource
from canopy_features.notifications.host_snapshot_producer import HostSnapshotProducer

CAPABILITY = {CAPABILITY_KEY: NATIVE_INTEROP, AVAILABLE_KEY: True}
MODULE_PATH = (Path(__file__).resolve().parents[1] / "canopy_features"
               / "notifications" / "daemon_interop.py")


class HostileMapping(Mapping):
    """Finite mapping that fails closed through one hostile dunder."""

    SECRET = "SECRET_MARKER"

    def __init__(self, data, mode="getitem"):
        self._data = data
        self._mode = mode

    def __getitem__(self, key):
        if self._mode == "getitem":
            raise RuntimeError(self.SECRET + " hostile lookup")
        return self._data[key]

    def __iter__(self):
        if self._mode == "iter":
            raise TypeError(self.SECRET + " hostile iteration")
        return iter(self._data)

    def __len__(self):
        if self._mode == "len":
            raise RuntimeError(self.SECRET + " hostile length")
        return len(self._data)


class TestNotificationDaemonInterop(unittest.TestCase):
    def _close(self, *objects):
        for obj in objects:
            try:
                obj.close()
            except Exception:
                pass

    def test_default_starts_unavailable_with_no_probes(self):
        interop = NotificationDaemonInterop()
        try:
            state = interop.state()
            self.assertEqual(state.status, UNAVAILABLE)
            self.assertEqual(state.reason, NO_SOURCE)
            self.assertIsNone(state.refusal)
            self.assertEqual(state.source_probe, NOT_PROBED)
            self.assertEqual(state.capability_probe, NOT_PROBED)
            self.assertEqual(state.probe_count, 0)
            self.assertEqual(state.loss_count, 0)
        finally:
            interop.close()

    def test_invalid_probe_bounds_are_rejected(self):
        for bad in (0, MAX_PROBES + 1, True, "3", 1.0, None, [], {}):
            with self.subTest(bad=bad), self.assertRaises(DaemonInteropError):
                interop = NotificationDaemonInterop(max_probes=bad)
                self._close(interop)

    def test_invalid_or_disconnected_source_fails_closed(self):
        dead = TrustedHostEventSource()
        dead.close()
        for bad in (object(), "source", 7, [], dead):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(DaemonInteropError):
                    NotificationDaemonInterop(source=bad)
        self._close(dead)

    def test_live_source_and_capability_probe_yields_available(self):
        interop = NotificationDaemonInterop()
        try:
            state = interop.probe(CAPABILITY)
            self.assertEqual(state.status, AVAILABLE)
            self.assertEqual(state.reason, NONE)
            self.assertIsNone(state.refusal)
            self.assertEqual(state.source_probe, SOURCE_LIVE)
            self.assertEqual(state.capability_probe, CAPABILITY_PRESENT)
            self.assertEqual(state.probe_count, 2)
        finally:
            interop.close()

    def test_probe_without_capability_stays_unavailable(self):
        interop = NotificationDaemonInterop()
        try:
            state = interop.probe()
            self.assertEqual(state.status, UNAVAILABLE)
            self.assertEqual(state.reason, CAPABILITY_ABSENT)
            self.assertEqual(state.source_probe, SOURCE_LIVE)
            self.assertIsNone(state.refusal)
        finally:
            interop.close()

    def test_capability_token_must_be_exact(self):
        for token in ("other", "native", NATIVE_INTEROP.upper(), "",
                      NATIVE_INTEROP + " ", 7, True, None, []):
            with self.subTest(token=token):
                interop = NotificationDaemonInterop(source=TrustedHostEventSource())
                try:
                    self.assertEqual(interop.probe_capability(
                        {CAPABILITY_KEY: token, AVAILABLE_KEY: True}),
                        CAPABILITY_ABSENT)
                    state = interop.state()
                    self.assertEqual(state.status, UNAVAILABLE)
                    self.assertEqual(state.reason, CAPABILITY_REFUSED)
                    self.assertEqual(state.refusal, INVALID_CAPABILITY)
                finally:
                    interop.close()

    def test_capability_available_flag_must_be_exact_true(self):
        for flag in (False, 1, "True", None, [], True):
            with self.subTest(flag=flag):
                interop = NotificationDaemonInterop(source=TrustedHostEventSource())
                try:
                    observation = {CAPABILITY_KEY: NATIVE_INTEROP,
                                   AVAILABLE_KEY: flag}
                    result = interop.probe_capability(observation)
                    if flag is True:
                        self.assertEqual(result, CAPABILITY_PRESENT)
                        self.assertEqual(interop.state().status, AVAILABLE)
                    else:
                        self.assertEqual(result, CAPABILITY_ABSENT)
                        self.assertEqual(interop.state().refusal,
                                         INVALID_CAPABILITY)
                finally:
                    interop.close()

    def test_extra_or_missing_capability_field_is_refused(self):
        cases = (
            {CAPABILITY_KEY: NATIVE_INTEROP, AVAILABLE_KEY: True, "extra": 1},
            {CAPABILITY_KEY: NATIVE_INTEROP},
            {AVAILABLE_KEY: True},
            {},
        )
        for observation in cases:
            with self.subTest(observation=observation):
                interop = NotificationDaemonInterop(
                    source=TrustedHostEventSource())
                try:
                    self.assertEqual(interop.probe_capability(observation),
                                     CAPABILITY_ABSENT)
                    self.assertEqual(interop.state().refusal,
                                     INVALID_CAPABILITY)
                finally:
                    interop.close()

    def test_wrong_observation_container_is_refused(self):
        for bad in (None, "capability", b"capability", 7, [], (), frozenset()):
            with self.subTest(bad=type(bad).__name__):
                interop = NotificationDaemonInterop(
                    source=TrustedHostEventSource())
                try:
                    self.assertEqual(interop.probe_capability(bad),
                                     CAPABILITY_ABSENT)
                    state = interop.state()
                    self.assertEqual(state.status, UNAVAILABLE)
                    self.assertEqual(state.refusal, INVALID_CAPABILITY)
                finally:
                    interop.close()

    def test_hostile_mapping_never_echoes_secret(self):
        for mode in ("getitem", "iter", "len"):
            with self.subTest(mode=mode):
                interop = NotificationDaemonInterop(
                    source=TrustedHostEventSource())
                try:
                    hostile = HostileMapping(CAPABILITY, mode=mode)
                    self.assertEqual(interop.probe_capability(hostile),
                                     CAPABILITY_ABSENT)
                    state = interop.state()
                    self.assertEqual(state.refusal, INVALID_CAPABILITY)
                    self.assertNotIn(HostileMapping.SECRET,
                                     repr(state.as_dict()))
                finally:
                    interop.close()

    def test_oversized_capability_token_is_refused(self):
        token = "a" * 65
        interop = NotificationDaemonInterop(source=TrustedHostEventSource())
        try:
            self.assertEqual(interop.probe_capability(
                {CAPABILITY_KEY: token, AVAILABLE_KEY: True}),
                CAPABILITY_ABSENT)
            self.assertEqual(interop.state().refusal, INVALID_CAPABILITY)
        finally:
            interop.close()

    def test_source_loss_fails_closed_and_clears_capability(self):
        source = TrustedHostEventSource()
        interop = NotificationDaemonInterop(source=source)
        self.assertEqual(interop.probe(CAPABILITY).status, AVAILABLE)
        source.close()
        self.assertEqual(interop.probe_source(), SOURCE_LOST)
        state = interop.state()
        self.assertEqual(state.status, UNAVAILABLE)
        self.assertEqual(state.reason, SOURCE_LOST)
        self.assertEqual(state.refusal, INVALID_SOURCE)
        self.assertEqual(state.capability_probe, NOT_PROBED)
        self.assertEqual(state.loss_count, 1)
        # A later capability observation cannot restore a lost source.
        self.assertEqual(interop.probe_capability(CAPABILITY),
                         CAPABILITY_ABSENT)
        self.assertEqual(interop.state().status, UNAVAILABLE)
        interop.close()

    def test_hostile_source_connected_probe_is_a_loss(self):
        source = TrustedHostEventSource()
        interop = NotificationDaemonInterop(source=source)
        try:
            source.connected = lambda: (_ for _ in ()).throw(
                RuntimeError("SECRET_MARKER hostile connected"))
            self.assertEqual(interop.probe_source(), SOURCE_LOST)
            state = interop.state()
            self.assertEqual(state.reason, SOURCE_LOST)
            self.assertEqual(state.refusal, INVALID_SOURCE)
            self.assertNotIn("SECRET_MARKER", repr(state.as_dict()))
        finally:
            interop.close()

    def test_non_true_source_connected_result_is_a_loss(self):
        for answer in (1, "yes", [], None, 0):
            with self.subTest(answer=answer):
                source = TrustedHostEventSource()
                interop = NotificationDaemonInterop(source=source)
                try:
                    source.connected = lambda answer=answer: answer
                    self.assertEqual(interop.probe_source(), SOURCE_LOST)
                    self.assertEqual(interop.state().status, UNAVAILABLE)
                finally:
                    interop.close()

    def test_probe_budget_is_bounded_and_fails_closed(self):
        interop = NotificationDaemonInterop(max_probes=2)
        try:
            self.assertEqual(interop.probe_source(), SOURCE_LIVE)
            self.assertEqual(interop.probe_capability(CAPABILITY),
                             CAPABILITY_PRESENT)
            self.assertEqual(interop.state().status, AVAILABLE)
            self.assertEqual(interop.probe_capability(CAPABILITY),
                             CAPABILITY_ABSENT)
            state = interop.state()
            self.assertEqual(state.status, UNAVAILABLE)
            self.assertEqual(state.reason, PROBE_LIMIT)
            self.assertEqual(state.refusal, PROBE_LIMIT)
            self.assertEqual(state.probe_count, 2)
        finally:
            interop.close()

    def test_reattach_rebases_probe_budget_and_reaches_available(self):
        source = TrustedHostEventSource()
        interop = NotificationDaemonInterop(source=source, max_probes=2)
        fresh = TrustedHostEventSource()
        try:
            self.assertEqual(interop.probe(CAPABILITY).status, AVAILABLE)
            self.assertEqual(interop.state().probe_count, 2)
            self.assertEqual(interop.probe_source(), SOURCE_LOST)
            state = interop.state()
            self.assertEqual(state.reason, PROBE_LIMIT)
            self.assertEqual(state.probe_count, 2)
            reattached = interop.reattach(fresh)
            self.assertEqual(reattached.probe_count, 1)
            self.assertEqual(interop.probe_capability(CAPABILITY),
                             CAPABILITY_PRESENT)
            state = interop.state()
            self.assertEqual(state.status, AVAILABLE)
            self.assertEqual(state.reason, NONE)
            self.assertEqual(state.probe_count, 2)
            self.assertEqual(state.loss_count, 0)
            # The new attachment has its own bounded budget, not an unbounded
            # probe stream.
            self.assertEqual(interop.probe_source(), SOURCE_LOST)
            self.assertEqual(interop.state().reason, PROBE_LIMIT)
            self.assertEqual(interop.state().probe_count, 2)
        finally:
            interop.close()
            self._close(source, fresh)

    def test_failed_reattach_does_not_rebase_probe_budget(self):
        source = TrustedHostEventSource()
        interop = NotificationDaemonInterop(source=source, max_probes=1)
        dead = TrustedHostEventSource()
        dead.close()
        try:
            self.assertEqual(interop.probe_source(), SOURCE_LIVE)
            self.assertEqual(interop.probe_source(), SOURCE_LOST)
            before = interop.state()
            self.assertEqual(before.reason, PROBE_LIMIT)
            for bad in (object(), "source", dead):
                with self.subTest(bad=type(bad).__name__):
                    with self.assertRaises(DaemonInteropError):
                        interop.reattach(bad)
            after = interop.state()
            self.assertEqual(after.reason, PROBE_LIMIT)
            self.assertEqual(after.probe_count, before.probe_count)
            self.assertEqual(after.refusal, PROBE_LIMIT)
        finally:
            interop.close()
            self._close(source, dead)

    def test_reattach_requires_a_trusted_live_source(self):
        source = TrustedHostEventSource()
        interop = NotificationDaemonInterop(source=source)
        source.close()
        interop.probe_source()
        dead = TrustedHostEventSource()
        dead.close()
        for bad in (object(), "source", dead):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(DaemonInteropError):
                    interop.reattach(bad)
        interop.close()
        self._close(dead)

    def test_reattach_clears_loss_but_requires_new_capability_probe(self):
        source = TrustedHostEventSource()
        interop = NotificationDaemonInterop(source=source)
        self.assertEqual(interop.probe(CAPABILITY).status, AVAILABLE)
        source.close()
        interop.probe_source()
        fresh = TrustedHostEventSource()
        interop.reattach(fresh)
        state = interop.state()
        self.assertEqual(state.status, UNAVAILABLE)
        self.assertEqual(state.reason, CAPABILITY_ABSENT)
        self.assertEqual(state.loss_count, 1)
        self.assertEqual(interop.probe(CAPABILITY).status, AVAILABLE)
        interop.close()
        self.assertTrue(fresh.connected())
        fresh.close()

    def test_close_is_explicit_unavailable_and_idempotent(self):
        interop = NotificationDaemonInterop()
        self.assertEqual(interop.probe(CAPABILITY).status, AVAILABLE)
        interop.close()
        interop.close()
        state = interop.state()
        self.assertEqual(state.status, UNAVAILABLE)
        self.assertEqual(state.reason, CLOSED)
        self.assertEqual(state.refusal, INTEROP_CLOSED)
        self.assertEqual(state.capability_probe, NOT_PROBED)
        with self.assertRaises(DaemonInteropError):
            interop.probe_source()
        with self.assertRaises(DaemonInteropError):
            interop.probe_capability(CAPABILITY)

    def test_injected_source_is_not_closed_by_interop(self):
        source = TrustedHostEventSource()
        interop = NotificationDaemonInterop(source=source)
        interop.close()
        self.assertTrue(source.connected())
        source.close()

    def test_snapshot_producer_is_an_accepted_trusted_source(self):
        producer = HostSnapshotProducer()
        interop = NotificationDaemonInterop(source=producer)
        try:
            self.assertEqual(interop.probe(CAPABILITY).status, AVAILABLE)
        finally:
            interop.close()
            producer.close()

    def test_state_is_frozen_and_snapshot_is_a_fresh_copy(self):
        interop = NotificationDaemonInterop()
        try:
            state = interop.probe(CAPABILITY)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                state.status = UNAVAILABLE
            view = state.as_dict()
            view["status"] = "tampered"
            self.assertEqual(state.status, AVAILABLE)
            self.assertIsNot(interop.state(), state)
        finally:
            interop.close()

    def test_no_transport_or_execution_imports(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        forbidden = {"os", "sys", "socket", "subprocess", "threading", "time",
                     "pathlib", "shutil", "tempfile", "asyncio", "dbus", "gi"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & forbidden)
        self.assertTrue({"collections", "dataclasses"} <= imported)

    def test_no_new_topic_or_side_effect_literals(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for banned in ("app.catalog.changed", "window.state.changed",
                       "session.state.changed", "capabilities.report",
                       ".notify-send", "gdbus", "notify_send"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
