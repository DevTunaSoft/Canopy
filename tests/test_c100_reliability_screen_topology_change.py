"""Offline unit tests for display topology recovery decisions.

No Qt, compositor, Linux Mint guest, real monitor or hardware event is used.
These tests exercise an in-memory model only, not a working desktop.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_core.host_events import HostEventsClosed
from canopy_features.reliability.screen_topology_change import (
    ACTIONS, DEFAULT_SUPPORTED_RESOLUTIONS, DISPLAY_STATES, MAX_MONITORS,
    Monitor, ScreenTopologyRecovery,
)


class ScreenTopologyRecoveryTests(unittest.TestCase):
    def test_no_monitors_enters_safe_mode(self):
        model = ScreenTopologyRecovery()
        event = model.observe([])
        self.assertEqual(event.action, "no_monitor")
        self.assertEqual(event.display_state, "safe")
        self.assertTrue(event.safe_mode)
        self.assertFalse(event.relocate_windows)
        self.assertEqual(event.monitor_count, 0)
        self.assertEqual((event.added, event.removed, event.fallback), ((), (), ()))
        self.assertEqual(event.sequence, 1)
        payload = model.host_events()[-1].payload
        self.assertEqual(payload["topology_action"], "no_monitor")
        self.assertTrue(payload["safe_mode"])
        self.assertLessEqual(len(payload), 8)
        with self.assertRaises(TypeError):
            payload["safe_mode"] = False
        model.close()

    def test_unsupported_resolution_falls_back_deterministically(self):
        cases = (
            ((1366, 768), (1280, 720)),
            ((8000, 8000), (3840, 2160)),
            ((10, 10), (640, 480)),
        )
        for (width, height), expected in cases:
            with self.subTest(resolution=(width, height)):
                model = ScreenTopologyRecovery()
                event = model.observe([Monitor("dvi", width, height)])
                self.assertEqual(event.action, "resolution_fallback")
                self.assertEqual(event.display_state, "reconfigured")
                self.assertEqual(event.fallback,
                                 (("dvi", expected[0], expected[1]),))
                self.assertFalse(event.safe_mode)
                self.assertEqual(
                    model.host_events()[-1].payload["fallback_count"], 1)
                model.close()

    def test_connect_disconnect_and_reconfigure_actions(self):
        model = ScreenTopologyRecovery()
        first = Monitor("DP-1", 1920, 1080)
        second = Monitor("HDMI-1", 1920, 1080)
        events = (
            model.observe([first]),
            model.observe([first, second]),
            model.observe([second]),
            model.observe([Monitor("HDMI-1", 1280, 720)]),
            model.observe([Monitor("DP-2", 1920, 1080)]),
        )
        self.assertEqual([e.action for e in events], [
            "connect", "connect", "disconnect", "resolution_changed",
            "reconfigure",
        ])
        self.assertEqual(events[1].added, ("HDMI-1",))
        self.assertEqual(events[2].removed, ("DP-1",))
        self.assertTrue(events[2].relocate_windows)
        self.assertEqual(events[3].changed, ("HDMI-1",))
        self.assertFalse(events[3].relocate_windows)
        self.assertEqual(events[4].added, ("DP-2",))
        self.assertEqual(events[4].removed, ("HDMI-1",))
        self.assertTrue(events[4].relocate_windows)
        self.assertEqual([e.sequence for e in events], [1, 2, 3, 4, 5])
        self.assertEqual(len(model.events()), 5)
        model.close()

    def test_stable_snapshot_reports_no_change(self):
        model = ScreenTopologyRecovery()
        display = Monitor("DP-1", 1920, 1080)
        model.observe([display])
        stable = model.observe([display])
        self.assertEqual(stable.action, "stable")
        self.assertEqual(stable.display_state, "active")
        self.assertEqual((stable.added, stable.removed, stable.changed),
                         ((), (), ()))
        self.assertEqual(stable.fallback, ())
        self.assertEqual(stable.sequence, 2)
        model.close()

    def test_bounded_history_and_input_rejection_keep_state_intact(self):
        model = ScreenTopologyRecovery(history=3)
        display = Monitor("DP-1", 1920, 1080)
        for _ in range(10):
            model.observe([display])
        self.assertEqual(len(model.events()), 3)
        self.assertEqual([e.sequence for e in model.events()], [8, 9, 10])

        bad_snapshots = (
            [Monitor(f"m{i}", 1280, 720) for i in range(MAX_MONITORS + 1)],
            [display, display],
            [("DP-1", 1920, 1080)],
            "DP-1",
        )
        for snapshot in bad_snapshots:
            with self.subTest(snapshot=repr(snapshot)[:40]):
                with self.assertRaises(ValueError):
                    model.observe(snapshot)
        self.assertEqual(len(model.events()), 3)

        for args in (("", 1920, 1080), ("x", 0, 1080), ("x", True, 1080),
                     ("x", 1920, 9000)):
            with self.subTest(monitor=args):
                with self.assertRaises(ValueError):
                    Monitor(*args)
        with self.assertRaises(ValueError):
            ScreenTopologyRecovery(history=0)
        with self.assertRaises(ValueError):
            ScreenTopologyRecovery(supported=set())
        with self.assertRaises(ValueError):
            ScreenTopologyRecovery(supported={(1920, 1080, 60)})

        self.assertEqual(model.observe([display]).sequence, 11)
        model.close()

    def test_custom_supported_resolution_suppresses_fallback(self):
        model = ScreenTopologyRecovery(supported={(1366, 768)})
        event = model.observe([Monitor("laptop", 1366, 768)])
        self.assertEqual(event.action, "connect")
        self.assertEqual(event.fallback, ())
        model.close()

    def test_recording_event_immutable_and_close_fails_closed(self):
        model = ScreenTopologyRecovery()
        event = model.observe([Monitor("DP-1", 1920, 1080)])
        with self.assertRaises(FrozenInstanceError):
            event.action = "stable"
        self.assertEqual(model.host_events()[0].payload["topology_action"],
                         "connect")
        model.close()
        model.close()
        self.assertTrue(model.closed)
        self.assertEqual((model.events(), model.host_events()), ((), ()))
        with self.assertRaises(HostEventsClosed):
            model.observe([Monitor("DP-1", 1920, 1080)])

    def test_vocabulary_and_no_polling_or_privileged_imports(self):
        self.assertLessEqual(
            {"no_monitor", "connect", "disconnect", "reconfigure",
             "resolution_changed", "resolution_fallback", "stable"}, ACTIONS)
        self.assertLessEqual({"safe", "active", "reconfigured"}, DISPLAY_STATES)
        self.assertIn((1920, 1080), DEFAULT_SUPPORTED_RESOLUTIONS)

        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/reliability/screen_topology_change.py")
        source = code.read_text(encoding="utf-8")
        for token in ("QTimer", "time.sleep", "Thread(", "import socket",
                      "subprocess", "asyncio", "importlib", "ctypes",
                      "requests", "urllib"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
