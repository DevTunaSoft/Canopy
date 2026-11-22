"""Offline unit tests for the accessible dock focus-order model.

No Qt runtime, compositor, real keyboard, desktop session or Linux Mint guest
is used. The QML order test reads committed source read-only; it does not build
or run the compiled prototype.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import re
import unittest

from canopy_features.dock.keyboard_navigation import (
    DEFAULT_TRANSITION_MS, MAX_ITEMS, DockFocusError, DockFocusOrder,
    FocusTransition,
)

ROOT = Path(__file__).resolve().parents[1]


class DockFocusOrderTests(unittest.TestCase):
    def test_empty_dock_has_no_focus_and_all_moves_are_no_ops(self):
        model = DockFocusOrder([])
        self.assertEqual(model.items, ())
        self.assertIsNone(model.focused_id)
        for action in (model.next, model.previous, model.focus_first,
                       model.focus_last, model.clear_focus):
            with self.subTest(action=action.__name__):
                transition = action()
                self.assertEqual(
                    (transition.from_id, transition.to_id, transition.moved,
                     transition.wrapped, transition.duration_ms),
                    (None, None, False, False, 0))
                self.assertIsNone(model.focused_id)
        with self.assertRaises(DockFocusError):
            model.focus("Browser")

    def test_next_and_previous_follow_dock_repeater_order(self):
        model = DockFocusOrder(["Browser", "Mail", "Files"])
        self.assertEqual(model.next().to_id, "Browser")
        self.assertEqual(model.next().to_id, "Mail")
        self.assertEqual(model.previous().to_id, "Browser")
        self.assertEqual(model.focused_id, "Browser")

    def test_wrap_moves_past_both_ends_when_enabled(self):
        model = DockFocusOrder(["Browser", "Mail", "Files"])
        self.assertEqual(model.previous().to_id, "Files")
        first = model.next()
        self.assertEqual((first.to_id, first.wrapped), ("Browser", True))
        self.assertEqual(model.focus_last().to_id, "Files")
        wrapped = model.next()
        self.assertEqual((wrapped.to_id, wrapped.wrapped), ("Browser", True))
        self.assertTrue(wrapped.moved)

    def test_no_wrap_stays_on_end_items(self):
        model = DockFocusOrder(["Browser", "Mail", "Files"], wrap=False)
        self.assertFalse(model.wrap)
        model.focus_last()
        stopped = model.next()
        self.assertEqual((stopped.from_id, stopped.to_id), ("Files", "Files"))
        self.assertFalse(stopped.moved)
        self.assertFalse(stopped.wrapped)
        self.assertEqual(stopped.duration_ms, 0)
        model.focus_first()
        stopped = model.previous()
        self.assertEqual((stopped.from_id, stopped.to_id), ("Browser", "Browser"))
        self.assertFalse(stopped.moved)
        self.assertFalse(stopped.wrapped)

    def test_focus_by_id_home_end_and_clear(self):
        model = DockFocusOrder(["Browser", "Mail", "Files"])
        self.assertEqual(model.focus("Files").to_id, "Files")
        self.assertEqual(model.focus_first().to_id, "Browser")
        self.assertEqual(model.focus_last().to_id, "Files")
        cleared = model.clear_focus()
        self.assertEqual((cleared.from_id, cleared.to_id), ("Files", None))
        self.assertTrue(cleared.moved)
        self.assertIsNone(model.focused_id)
        for bad in ("Missing", "", None, 3):
            with self.subTest(bad=bad):
                with self.assertRaises(DockFocusError):
                    model.focus(bad)

    def test_reduced_motion_zeroes_transition_duration(self):
        normal = DockFocusOrder(["Browser", "Mail"])
        reduced = DockFocusOrder(["Browser", "Mail"], reduced_motion=True)
        self.assertTrue(reduced.reduced_motion)
        self.assertEqual(normal.next().duration_ms, DEFAULT_TRANSITION_MS)
        self.assertEqual(reduced.next().duration_ms, 0)
        self.assertEqual(reduced.next().duration_ms, 0)  # wrapped, still silent
        self.assertEqual(reduced.clear_focus().duration_ms, 0)
        normal.clear_focus()
        # Reduced motion never changes the focus order itself.
        self.assertEqual(normal.items, reduced.items)
        self.assertEqual(normal.focused_id, reduced.focused_id)

    def test_set_items_keeps_or_clears_focus_without_geometry(self):
        model = DockFocusOrder(["Browser", "Mail", "Files"])
        model.focus("Mail")
        kept = model.set_items(["Files", "Mail"])
        self.assertEqual((kept.to_id, kept.moved, model.focused_id),
                         ("Mail", False, "Mail"))
        dropped = model.set_items(["Files", "Terminal"])
        self.assertEqual((dropped.from_id, dropped.to_id, dropped.moved),
                         ("Mail", None, True))
        self.assertIsNone(model.focused_id)
        self.assertEqual(model.items, ("Files", "Terminal"))

    def test_set_items_is_atomic_on_invalid_input(self):
        model = DockFocusOrder(["Browser", "Mail"])
        model.focus("Mail")
        with self.assertRaises(DockFocusError):
            model.set_items(["Files", "Files"])
        self.assertEqual(model.items, ("Browser", "Mail"))
        self.assertEqual(model.focused_id, "Mail")

    def test_validation_rejects_invalid_bounded_item_lists(self):
        invalid = [
            ["Browser", "Browser"], ["Browser", ""], ["Browser", 3],
            "Browser", b"Browser", {"a": 1}, {"a", "b"}, (x for x in ["a"]),
            ["i%d" % n for n in range(MAX_ITEMS + 1)],
        ]
        for items in invalid:
            with self.subTest(items=repr(items)[:40]):
                with self.assertRaises(DockFocusError):
                    DockFocusOrder(items)
        for option in ({"wrap": 1}, {"reduced_motion": "yes"}):
            with self.subTest(option=option):
                with self.assertRaises(DockFocusError):
                    DockFocusOrder(["Browser"], **option)
        self.assertEqual(len(DockFocusOrder(["i%d" % n
                                             for n in range(MAX_ITEMS)]).items),
                         MAX_ITEMS)

    def test_order_and_transition_are_immutable(self):
        model = DockFocusOrder(["Browser", "Mail"])
        original = model.items
        model.set_items(["Mail", "Browser"])
        self.assertEqual(original, ("Browser", "Mail"))
        with self.assertRaises(TypeError):
            model.items[0] = "Files"
        transition = FocusTransition("Browser", "Mail", True, False, 120)
        with self.assertRaises(FrozenInstanceError):
            transition.to_id = "Files"
        self.assertEqual(transition.active_id, "Mail")

    def test_model_can_represent_actual_frozen_qml_dock_order(self):
        # Read-only check against the real compiled prototype source.
        source = (ROOT / "prototype" / "classic" / "Main.qml").read_text(
            encoding="utf-8")
        match = re.search(r"model:\s*canopyApprovedMode\s*\?\s*\[(.*?)\]\s*:",
                          source, re.DOTALL)
        self.assertIsNotNone(match)
        titles = re.findall(r'title:\s*"([^"]+)"', match.group(1))
        self.assertEqual(len(titles), 8)

        model = DockFocusOrder(titles)
        for _ in titles:
            model.next()
        self.assertEqual(model.focused_id, titles[-1])
        wrapped = model.next()
        self.assertEqual((wrapped.to_id, wrapped.wrapped), (titles[0], True))

    def test_no_polling_threads_network_or_io(self):
        code = (ROOT / "canopy_features" / "dock" /
                "keyboard_navigation.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import subprocess", "QTimer",
                          "time.sleep", "Thread(", "asyncio", "while True",
                          "importlib", "open("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
