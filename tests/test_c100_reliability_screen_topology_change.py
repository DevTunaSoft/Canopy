"""Offline unit tests for the bounded screen-topology recovery model.

No real display, Qt build, Linux Mint guest or compiled application is used.
These tests validate pure-Python decision logic and boundary handling only.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.reliability.screen_topology_change import (
    ACTION_CLAMP_RESOLUTION, ACTION_NO_OP, ACTION_REANCHOR_PRIMARY,
    ACTION_RELAYOUT, ACTION_RESUME, ACTION_SUSPEND,
    EVENT_CONNECT, EVENT_DISCONNECT, EVENT_PRIMARY_CHANGED,
    EVENT_RESOLUTION_CHANGED, MAX_HISTORY, MAX_MONITORS,
    SUPPORTED_RESOLUTIONS, Change, Monitor, RecoveryAction, ScreenTopologyModel,
    Topology, TopologyError, nearest_supported_resolution,
)


def topo(*monitors):
    return Topology(list(monitors))


class ScreenTopologyModelTests(unittest.TestCase):
    def test_initial_observation_then_no_op_when_unchanged(self):
        model = ScreenTopologyModel()
        first = model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        self.assertEqual([c.kind for c in first.changes], [EVENT_CONNECT])
        self.assertIn(ACTION_RESUME, first.action_kinds)
        second = model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        self.assertEqual(second.changes, ())
        self.assertEqual(second.action_kinds, (ACTION_NO_OP,))
        self.assertEqual((first.sequence, second.sequence), (1, 2))

    def test_connect_and_disconnect_events(self):
        model = ScreenTopologyModel()
        model.apply(topo(Monitor("HDMI-1", 1920, 1080, True),
                         Monitor("DP-1", 2560, 1440)))
        result = model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        self.assertEqual([(c.kind, c.connector) for c in result.changes],
                         [(EVENT_DISCONNECT, "DP-1")])
        self.assertIn(ACTION_RELAYOUT, result.action_kinds)
        self.assertEqual(result.safe_topology.connectors, frozenset({"HDMI-1"}))

    def test_no_monitors_suspends_then_resumes(self):
        model = ScreenTopologyModel()
        model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        empty = model.apply(Topology(()))
        self.assertEqual([c.kind for c in empty.changes], [EVENT_DISCONNECT])
        self.assertEqual(empty.action_kinds, (ACTION_SUSPEND,))
        self.assertTrue(empty.safe_topology.is_empty)
        self.assertTrue(model.current.is_empty)
        resumed = model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        self.assertEqual([c.kind for c in resumed.changes], [EVENT_CONNECT])
        self.assertIn(ACTION_RESUME, resumed.action_kinds)

    def test_empty_initial_observation_suspends_without_changes(self):
        model = ScreenTopologyModel()
        result = model.apply(Topology(()))
        self.assertEqual(result.changes, ())
        self.assertEqual(result.action_kinds, (ACTION_SUSPEND,))

    def test_unsupported_resolution_is_detected_and_clamped(self):
        monitor = Monitor("DP-2", 1280, 800)
        self.assertNotIn(monitor.resolution, SUPPORTED_RESOLUTIONS)
        self.assertFalse(monitor.supported)
        result = ScreenTopologyModel().apply(topo(monitor))
        self.assertIn(ACTION_CLAMP_RESOLUTION, result.action_kinds)
        clamped_action = next(a for a in result.actions
                              if a.kind == ACTION_CLAMP_RESOLUTION)
        self.assertEqual(clamped_action.detail, ("DP-2",))
        safe = result.safe_topology.monitors[0]
        self.assertEqual(safe.resolution, (1280, 720))
        self.assertTrue(safe.supported)

    def test_multiple_unsupported_resolutions_are_bounded_and_sorted(self):
        result = ScreenTopologyModel().apply(topo(
            Monitor("DP-9", 999, 999),
            Monitor("DP-1", 1280, 800),
            Monitor("HDMI-1", 1920, 1080, True),
        ))
        action = next(a for a in result.actions
                      if a.kind == ACTION_CLAMP_RESOLUTION)
        self.assertEqual(action.detail, ("DP-1", "DP-9"))
        for monitor in result.safe_topology.monitors:
            self.assertTrue(monitor.supported)

    def test_nearest_supported_resolution_is_deterministic(self):
        self.assertEqual(nearest_supported_resolution(1280, 800), (1280, 720))
        self.assertEqual(nearest_supported_resolution(1920, 1200), (1920, 1080))
        for width, height in ((1, 1), (7680, 4320), (1290, 740)):
            with self.subTest(size=(width, height)):
                nearest = nearest_supported_resolution(width, height)
                self.assertIn(nearest, SUPPORTED_RESOLUTIONS)

    def test_resolution_change_event_carries_old_and_new(self):
        model = ScreenTopologyModel()
        model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        result = model.apply(topo(Monitor("HDMI-1", 2560, 1440, True)))
        self.assertEqual([c.kind for c in result.changes],
                         [EVENT_RESOLUTION_CHANGED])
        self.assertEqual(result.changes[0].detail,
                         ((1920, 1080), (2560, 1440)))
        self.assertIn(ACTION_RELAYOUT, result.action_kinds)

    def test_primary_changed_event_reanchors(self):
        model = ScreenTopologyModel()
        model.apply(topo(Monitor("HDMI-1", 1920, 1080, True),
                         Monitor("DP-1", 2560, 1440)))
        flipped = model.apply(topo(Monitor("HDMI-1", 1920, 1080),
                                   Monitor("DP-1", 2560, 1440, True)))
        self.assertIn(EVENT_PRIMARY_CHANGED,
                      [c.kind for c in flipped.changes])
        self.assertIn(ACTION_REANCHOR_PRIMARY, flipped.action_kinds)

    def test_primary_disconnect_reanchors_to_remaining_monitor(self):
        model = ScreenTopologyModel()
        model.apply(topo(Monitor("HDMI-1", 1920, 1080, True),
                         Monitor("DP-1", 2560, 1440)))
        disconnected = model.apply(topo(Monitor("DP-1", 2560, 1440)))
        self.assertEqual([(c.kind, c.connector) for c in disconnected.changes],
                         [(EVENT_DISCONNECT, "HDMI-1")])
        self.assertIn(ACTION_REANCHOR_PRIMARY, disconnected.action_kinds)
        self.assertEqual(disconnected.safe_topology.primary.connector, "DP-1")

    def test_safe_topology_always_has_one_primary_when_nonempty(self):
        for monitors in ((Monitor("DP-1", 1920, 1080),),
                         (Monitor("DP-1", 1920, 1080, True),
                          Monitor("HDMI-1", 1920, 1080))):
            with self.subTest(monitors=monitors):
                result = ScreenTopologyModel().apply(topo(*monitors))
                primary = result.safe_topology.primary
                self.assertIsNotNone(primary)
                self.assertEqual(sum(1 for m in result.safe_topology.monitors
                                     if m.primary), 1)

    def test_invalid_monitor_geometry_and_connector_rejected(self):
        bad_monitors = (
            ("", 1920, 1080, False), ("bad connector", 1920, 1080, False),
            ("A" * 65, 1920, 1080, False), ("HDMI-1", 0, 1080, False),
            ("HDMI-1", 1920, -1, False), ("HDMI-1", 7681, 1080, False),
            ("HDMI-1", 1920, 4321, False), ("HDMI-1", True, 1080, False),
            ("HDMI-1", 1920, 1080, 1), ("HDMI-1", 1920, 1080, "yes"),
            (1, 1920, 1080, False),
        )
        for connector, width, height, primary in bad_monitors:
            with self.subTest(connector=connector, width=width,
                              height=height, primary=primary):
                with self.assertRaises(TopologyError):
                    Monitor(connector, width, height, primary)

    def test_invalid_topology_rejected(self):
        for monitors in (
            [Monitor("DP-1", 1920, 1080, True),
             Monitor("DP-1", 1920, 1080)],
            [Monitor("DP-1", 1920, 1080, True),
             Monitor("HDMI-1", 1920, 1080, True)],
            [Monitor("X-%d" % i, 1920, 1080) for i in range(MAX_MONITORS + 1)],
            [Monitor("DP-1", 1920, 1080), "not-a-monitor"],
            "not-a-sequence",
        ):
            with self.subTest(monitors=repr(monitors)[:60]):
                with self.assertRaises(TopologyError):
                    Topology(monitors)

    def test_apply_requires_topology_and_history_limit_is_bounded(self):
        model = ScreenTopologyModel()
        for value in (Monitor("DP-1", 1920, 1080), [Monitor("DP-1", 1920, 1080)],
                      None):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TopologyError):
                    model.apply(value)
        for limit in (0, -1, MAX_HISTORY + 1, True, 3.0, "3"):
            with self.subTest(limit=limit):
                with self.assertRaises(TopologyError):
                    ScreenTopologyModel(history_limit=limit)

    def test_history_is_bounded_and_monotonic(self):
        model = ScreenTopologyModel(history_limit=3)
        for index in range(MAX_HISTORY):
            model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
            self.assertLessEqual(len(model.history), 3)
        self.assertEqual(len(model.history), 3)
        self.assertEqual([r.sequence for r in model.history],
                         [MAX_HISTORY - 2, MAX_HISTORY - 1, MAX_HISTORY])

    def test_reset_clears_current_and_history(self):
        model = ScreenTopologyModel()
        model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        model.reset()
        self.assertIsNone(model.current)
        self.assertEqual(model.history, ())
        self.assertEqual(model.apply(topo(Monitor("HDMI-1", 1920, 1080, True))).sequence,
                         1)

    def test_results_and_inputs_are_immutable(self):
        monitor = Monitor("HDMI-1", 1920, 1080, True)
        with self.assertRaises(FrozenInstanceError):
            monitor.width = 800
        result = ScreenTopologyModel().apply(topo(monitor))
        with self.assertRaises(FrozenInstanceError):
            result.sequence = 99
        with self.assertRaises(TypeError):
            result.changes[0] = Change(EVENT_CONNECT, "x")

    def test_no_polling_thread_service_or_network_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/reliability/screen_topology_change.py").read_text()
        for banned in ("QTimer", "QGuiApplication", "asyncio", "subprocess",
                       "import socket", "Thread(", "importlib", "time.sleep",
                       "while True", "import time", "import threading"):
            with self.subTest(token=banned):
                self.assertNotIn(banned, code)

    def test_change_and_action_contracts(self):
        self.assertEqual(Change(EVENT_CONNECT, "DP-1").detail, ())
        self.assertEqual(Change(EVENT_CONNECT, "DP-1").connector, "DP-1")
        self.assertEqual(RecoveryAction(ACTION_NO_OP).detail, ())
        self.assertEqual(RecoveryAction(ACTION_NO_OP, ("x",)).detail, ("x",))


class ContradictoryTopologyStateTests(unittest.TestCase):
    """Decision inputs must come from durable, validated topology state."""

    def test_lying_empty_flag_cannot_manufacture_suspend(self):
        class LyingEmptyTopology(Topology):
            @property
            def is_empty(self):
                return True

        topology = LyingEmptyTopology([Monitor("HDMI-1", 1920, 1080, True)])
        with self.assertRaises(TopologyError):
            ScreenTopologyModel().apply(topology)

    def test_lying_primary_flag_cannot_manufacture_reanchor(self):
        class LyingPrimaryTopology(Topology):
            @property
            def primary(self):
                return None

        model = ScreenTopologyModel()
        model.apply(topo(Monitor("HDMI-1", 1920, 1080, True)))
        hostile = LyingPrimaryTopology([
            Monitor("HDMI-1", 1920, 1080, True), Monitor("DP-1", 1920, 1080)])
        with self.assertRaises(TopologyError):
            model.apply(hostile)

    def test_spoofed_connector_label_cannot_manufacture_connect(self):
        class SpoofedConnector(Monitor):
            def __init__(self):
                object.__setattr__(self, "width", 1920)
                object.__setattr__(self, "height", 1080)
                object.__setattr__(self, "primary", False)

            @property
            def connector(self):
                return "HDMI-1"

        with self.assertRaises(TopologyError):
            ScreenTopologyModel().apply(Topology([SpoofedConnector()]))


if __name__ == "__main__":
    unittest.main()
