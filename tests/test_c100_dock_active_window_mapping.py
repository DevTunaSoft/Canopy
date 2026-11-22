"""Offline tests for focused-window -> trusted-dock-tile mapping.

No real Mint, compositor or compiled Qt is exercised here. Focus events are
synthetic and the host event bus is the in-process primitive from
canopy_core. Integration into the compiled Qt application remains future
work and is not claimed by these tests.
"""
import json
from pathlib import Path
import unittest

from canopy_features.dock.active_window_mapping import (
    ActiveWindowMapping, DEFAULT_OWNER_TILES, FocusEvent, MappingError,
    MAPPED, STALE_EVENT, IGNORED, UNKNOWN_OWNER, WINDOW_CLOSED, TRUSTED_TILES,
)

ROOT = Path(__file__).resolve().parents[1]


class ActiveWindowMappingTests(unittest.TestCase):
    def test_maps_focused_window_to_trusted_tile(self):
        mapper = ActiveWindowMapping()
        result = mapper.on_focus(FocusEvent(42, "nemo.desktop", 1))
        self.assertEqual((result.status, result.window_id, result.tile),
                         (MAPPED, 42, "Files"))
        self.assertTrue(result.active)
        self.assertEqual((mapper.state.window_id, mapper.state.tile,
                          mapper.state.sequence), (42, "Files", 1))

    def test_unknown_owner_fails_closed(self):
        mapper = ActiveWindowMapping()
        result = mapper.on_focus(FocusEvent(9, "unlisted.app", 4))
        self.assertEqual(result.status, UNKNOWN_OWNER)
        self.assertIsNone(result.tile)
        self.assertFalse(result.active)
        self.assertIsNone(mapper.state.tile)
        # Unknown input never grows the allowlist.
        self.assertNotIn("unlisted.app", mapper.owner_tiles)
        self.assertEqual(len(mapper.owner_tiles), len(DEFAULT_OWNER_TILES))

    def test_stale_out_of_order_focus_is_ignored(self):
        mapper = ActiveWindowMapping()
        mapper.on_focus(FocusEvent(1, "firefox.desktop", 5))
        # A late event for a different app with an older sequence must not win.
        stale = mapper.on_focus(FocusEvent(2, "gnome-terminal.desktop", 3))
        self.assertEqual(stale.status, STALE_EVENT)
        self.assertEqual(mapper.state.tile, "Browser")
        self.assertEqual(mapper.state.window_id, 1)
        self.assertEqual(mapper.state.sequence, 5)

    def test_equal_sequence_last_writer_wins(self):
        mapper = ActiveWindowMapping()
        mapper.on_focus(FocusEvent(1, "firefox.desktop", 2))
        result = mapper.on_focus(FocusEvent(2, "thunderbird.desktop", 2))
        self.assertEqual(result.status, MAPPED)
        self.assertEqual(mapper.state.tile, "Mail")

    def test_newer_focus_replaces_tile(self):
        mapper = ActiveWindowMapping()
        mapper.on_focus(FocusEvent(1, "firefox.desktop", 1))
        result = mapper.on_focus(FocusEvent(2, "gnome-terminal.desktop", 2))
        self.assertEqual(result.tile, "Terminal")
        self.assertEqual(mapper.state.window_id, 2)

    def test_close_only_clears_matching_non_stale_window(self):
        mapper = ActiveWindowMapping()
        mapper.on_focus(FocusEvent(10, "nemo.desktop", 5))
        # Different window, newer sequence: no effect.
        self.assertEqual(mapper.window_closed(11, 6).status, IGNORED)
        # Matching window but stale sequence: no effect.
        self.assertEqual(mapper.window_closed(10, 4).status, STALE_EVENT)
        self.assertEqual(mapper.state.tile, "Files")
        # Matching window, newer sequence: cleared.
        result = mapper.window_closed(10, 7)
        self.assertEqual(result.status, WINDOW_CLOSED)
        self.assertIsNone(mapper.state.tile)
        self.assertIsNone(mapper.state.window_id)
        self.assertEqual(mapper.state.sequence, 7)

    def test_unknown_owner_then_known_owner_recovers(self):
        mapper = ActiveWindowMapping()
        mapper.on_focus(FocusEvent(1, "mystery.app", 1))
        self.assertIsNone(mapper.state.tile)
        result = mapper.on_focus(FocusEvent(2, "org.gnome.Settings.desktop", 2))
        self.assertEqual(result.tile, "Settings")

    def test_clear_drops_focus_but_keeps_allowlist(self):
        mapper = ActiveWindowMapping()
        mapper.on_focus(FocusEvent(1, "nemo.desktop", 3))
        mapper.clear()
        self.assertIsNone(mapper.state.tile)
        self.assertEqual(mapper.state.sequence, 3)
        self.assertEqual(mapper.on_focus(FocusEvent(2, "nemo.desktop", 4)).tile,
                         "Files")

    def test_allowlist_rejects_untrusted_tile(self):
        for bad in ({"firefox.desktop": "EvilTile"},
                    {"firefox.desktop": "browser"},
                    {"firefox.desktop": ""},
                    {"firefox.desktop": 1}):
            with self.subTest(bad=bad):
                with self.assertRaises(MappingError):
                    ActiveWindowMapping(bad)

    def test_allowlist_rejects_invalid_owner_and_bounds(self):
        cases = [
            {"": "Files"},
            {"x" * 129: "Files"},
            {7: "Files"},
            {f"owner{i}.desktop": "Files" for i in range(257)},
            ["not", "a", "mapping"],
        ]
        for bad in cases:
            with self.subTest(kind=type(bad).__name__, size=len(bad)):
                with self.assertRaises(MappingError):
                    ActiveWindowMapping(bad)

    def test_allowlist_is_immutable_copy(self):
        source = {"firefox.desktop": "Browser"}
        mapper = ActiveWindowMapping(source)
        source["extra.desktop"] = "Files"
        with self.assertRaises(TypeError):
            mapper.owner_tiles["extra.desktop"] = "Files"
        self.assertNotIn("extra.desktop", mapper.owner_tiles)

    def test_focus_event_validation(self):
        for args in (
            (0, "nemo.desktop", 1),
            (-1, "nemo.desktop", 1),
            (True, "nemo.desktop", 1),
            (1_000_000_000_001, "nemo.desktop", 1),
            (1, "", 1),
            (1, "x" * 129, 1),
            (1, 5, 1),
            (1, "nemo.desktop", -1),
            (1, "nemo.desktop", True),
        ):
            with self.subTest(args=args):
                with self.assertRaises(MappingError):
                    FocusEvent(*args)

    def test_bad_event_type_is_rejected(self):
        with self.assertRaises(MappingError):
            ActiveWindowMapping().on_focus((1, "nemo.desktop", 1))

    def test_closed_validation(self):
        mapper = ActiveWindowMapping()
        for args in ((0, 1), (1, -1), (True, 1), (1, True)):
            with self.subTest(args=args):
                with self.assertRaises(MappingError):
                    mapper.window_closed(*args)

    def test_trusted_tiles_match_approved_manifest(self):
        manifest = (ROOT / "prototype" / "classic" / "assets" / "approved"
                    / "manifest.json")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        names = frozenset(item["name"] for item in data["icons"])
        self.assertEqual(names, TRUSTED_TILES)

    def test_default_allowlist_targets_only_trusted_unambiguous_tiles(self):
        self.assertTrue(set(DEFAULT_OWNER_TILES.values()).issubset(TRUSTED_TILES))
        self.assertNotIn("org.gnome.Evolution.desktop", DEFAULT_OWNER_TILES)

    def test_host_event_bus_integration(self):
        from canopy_core.host_events import HostEvents

        mapper = ActiveWindowMapping()
        callback = mapper.on_window_event  # stable identity for allowlist
        bus = HostEvents({"window.state.changed": [callback]})
        bus.subscribe("window.state.changed", callback)

        first = bus.emit("window.state.changed", {
            "window_id": 7, "owner": "nemo.desktop", "sequence": 1,
            "state": "focused",
        })
        self.assertEqual((first.delivered, first.callback_failures), (1, 0))
        self.assertEqual(mapper.state.tile, "Files")
        with self.assertRaises(TypeError):
            first.event.payload["owner"] = "firefox.desktop"

        # A late event on the bus with an older sequence is ignored.
        bus.emit("window.state.changed", {
            "window_id": 8, "owner": "firefox.desktop", "sequence": 0,
            "state": "focused",
        })
        self.assertEqual(mapper.state.tile, "Files")

        # Closed needs no owner and clears a matching focus.
        bus.emit("window.state.changed", {
            "window_id": 7, "sequence": 2, "state": "closed",
        })
        self.assertIsNone(mapper.state.tile)

        # An unknown state is ignored without changing focus.
        bus.emit("window.state.changed", {
            "window_id": 9, "owner": "firefox.desktop", "sequence": 3,
            "state": "minimized",
        })
        self.assertIsNone(mapper.state.tile)
        bus.close()

    def test_no_polling_or_privileged_imports(self):
        code = (ROOT / "canopy_features" / "dock"
                / "active_window_mapping.py").read_text(encoding="utf-8")
        for forbidden in ("QTimer", "asyncio", "import subprocess",
                          "import socket", "Thread(", "importlib",
                          "time.sleep", "open(", "os.system",
                          "import ctypes"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
