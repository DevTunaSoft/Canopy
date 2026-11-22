"""Offline unit tests for the pure optional dock auto-hide state machine.

No Qt, display, Mint session or compiled binary is used here. These checks
exercise only the pure Python model and its source-level inertness.
"""
from dataclasses import FrozenInstanceError, fields
from itertools import product
from pathlib import Path
import unittest

from canopy_features.dock.autohide_state import (
    AutoHideMode, DockEvent, DockVisibility, initial_state, transition,
)


SOURCE = (Path(__file__).resolve().parents[1] /
          "canopy_features" / "dock" / "autohide_state.py")


class DockAutoHideStateTests(unittest.TestCase):
    def test_default_is_opt_in_and_always_visible(self):
        state = initial_state()
        self.assertEqual(state.mode, AutoHideMode.OFF)
        self.assertFalse(state.revealed)
        self.assertTrue(state.focused)
        self.assertFalse(state.modal_active)
        self.assertTrue(state.visible)

    def test_enable_retracts_and_disable_restores_visibility(self):
        enabled = transition(initial_state(), DockEvent.ENABLE_AUTO_HIDE)
        self.assertEqual(enabled.mode, AutoHideMode.ON)
        self.assertFalse(enabled.revealed)
        self.assertFalse(enabled.visible)
        self.assertEqual(transition(enabled, DockEvent.ENABLE_AUTO_HIDE), enabled)
        self.assertEqual(transition(enabled, DockEvent.DISABLE_AUTO_HIDE),
                         initial_state())
        self.assertTrue(transition(enabled, DockEvent.DISABLE_AUTO_HIDE).visible)

    def test_pointer_reveal_and_leave_only_when_auto_hide_on(self):
        off = initial_state()
        self.assertFalse(transition(off, DockEvent.POINTER_ENTER_REVEAL_ZONE).revealed)
        self.assertTrue(transition(off, DockEvent.POINTER_ENTER_REVEAL_ZONE).visible)

        on = transition(off, DockEvent.ENABLE_AUTO_HIDE)
        revealed = transition(on, DockEvent.POINTER_ENTER_REVEAL_ZONE)
        self.assertTrue(revealed.revealed)
        self.assertTrue(revealed.visible)
        left = transition(revealed, DockEvent.POINTER_LEAVE_REVEAL_ZONE)
        self.assertFalse(left.revealed)
        self.assertFalse(left.visible)

    def test_reveal_requires_focus_and_no_modal(self):
        for focused, modal in product((False, True), repeat=2):
            with self.subTest(focused=focused, modal=modal):
                state = DockVisibility(
                    mode=AutoHideMode.ON, revealed=False,
                    focused=focused, modal_active=modal,
                )
                after = transition(state, DockEvent.POINTER_ENTER_REVEAL_ZONE)
                self.assertEqual(after.revealed, focused and not modal)
                self.assertEqual(after.visible, focused and not modal)

    def test_focus_loss_retracts_and_blocks_stale_reveal(self):
        on = transition(initial_state(), DockEvent.ENABLE_AUTO_HIDE)
        revealed = transition(on, DockEvent.POINTER_ENTER_REVEAL_ZONE)
        lost = transition(revealed, DockEvent.FOCUS_LOST)
        self.assertFalse(lost.focused)
        self.assertFalse(lost.revealed)
        self.assertFalse(lost.visible)
        self.assertEqual(transition(lost, DockEvent.FOCUS_LOST), lost)
        self.assertFalse(transition(lost, DockEvent.POINTER_ENTER_REVEAL_ZONE).revealed)

        gained = transition(lost, DockEvent.FOCUS_GAINED)
        self.assertTrue(gained.focused)
        self.assertFalse(gained.revealed)
        self.assertTrue(transition(gained, DockEvent.POINTER_ENTER_REVEAL_ZONE).revealed)

    def test_modal_retracts_and_suppresses_reveal_until_closed(self):
        on = transition(initial_state(), DockEvent.ENABLE_AUTO_HIDE)
        revealed = transition(on, DockEvent.POINTER_ENTER_REVEAL_ZONE)
        modal = transition(revealed, DockEvent.MODAL_OPENED)
        self.assertTrue(modal.modal_active)
        self.assertFalse(modal.revealed)
        self.assertFalse(modal.visible)
        self.assertEqual(transition(modal, DockEvent.MODAL_OPENED), modal)
        self.assertFalse(transition(modal, DockEvent.POINTER_ENTER_REVEAL_ZONE).revealed)

        closed = transition(modal, DockEvent.MODAL_CLOSED)
        self.assertFalse(closed.modal_active)
        self.assertFalse(closed.revealed)
        self.assertTrue(transition(closed, DockEvent.POINTER_ENTER_REVEAL_ZONE).revealed)

    def test_disable_wins_over_hidden_and_modal_then_re_enable_hides(self):
        on = transition(initial_state(), DockEvent.ENABLE_AUTO_HIDE)
        modal = transition(on, DockEvent.MODAL_OPENED)
        always_visible = transition(modal, DockEvent.DISABLE_AUTO_HIDE)
        self.assertTrue(always_visible.visible)
        self.assertFalse(always_visible.revealed)
        self.assertTrue(always_visible.modal_active)

        re_enabled = transition(always_visible, DockEvent.ENABLE_AUTO_HIDE)
        self.assertFalse(re_enabled.visible)
        self.assertTrue(re_enabled.modal_active)
        unfocused = transition(on, DockEvent.FOCUS_LOST)
        self.assertTrue(transition(unfocused, DockEvent.DISABLE_AUTO_HIDE).visible)

    def test_all_state_event_edges_keep_invariants_and_bounded_shape(self):
        checked = 0
        valid_states = 0
        for mode, revealed, focused, modal in product(
                AutoHideMode, (False, True), (False, True), (False, True)):
            if revealed and (mode is AutoHideMode.OFF or not focused or modal):
                with self.subTest(mode=mode, revealed=revealed,
                                  focused=focused, modal=modal):
                    with self.assertRaises(ValueError):
                        DockVisibility(mode, revealed, focused, modal)
                continue
            valid_states += 1
            state = DockVisibility(mode, revealed, focused, modal)
            before = tuple(getattr(state, f.name) for f in fields(state))
            for event in DockEvent:
                after = transition(state, event)
                self.assertIsInstance(after, DockVisibility)
                self.assertEqual(tuple(getattr(state, f.name) for f in fields(state)),
                                 before, "input state was mutated")
                self.assertEqual({f.name for f in fields(after)},
                                 {"mode", "revealed", "focused", "modal_active"})
                if after.mode is AutoHideMode.OFF:
                    self.assertTrue(after.visible)
                if after.revealed:
                    self.assertIs(after.mode, AutoHideMode.ON)
                    self.assertTrue(after.focused)
                    self.assertFalse(after.modal_active)
                if not after.focused or after.modal_active:
                    self.assertFalse(after.revealed)
                checked += 1
        self.assertEqual(checked, valid_states * len(DockEvent))
        self.assertGreater(valid_states, 0)

    def test_transition_is_pure_frozen_and_deterministic(self):
        state = transition(initial_state(), DockEvent.ENABLE_AUTO_HIDE)
        with self.assertRaises(FrozenInstanceError):
            state.revealed = True
        first = transition(state, DockEvent.POINTER_ENTER_REVEAL_ZONE)
        second = transition(state, DockEvent.POINTER_ENTER_REVEAL_ZONE)
        self.assertIsNot(first, state)
        self.assertEqual(first, second)
        self.assertFalse(state.revealed)
        self.assertEqual(len(AutoHideMode), 2)
        self.assertEqual(len(DockEvent), 8)

    def test_strict_input_validation(self):
        state = initial_state()
        for bad in ("enable_auto_hide", True, 1, None, DockVisibility):
            with self.subTest(event=bad), self.assertRaises(TypeError):
                transition(state, bad)
        for bad in (None, "off", 0, True):
            with self.subTest(state=bad), self.assertRaises(TypeError):
                transition(bad, DockEvent.ENABLE_AUTO_HIDE)
        for kwargs in ({"mode": "off"}, {"revealed": 1}, {"focused": None},
                       {"modal_active": "yes"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(TypeError):
                DockVisibility(**kwargs)

    def test_source_has_no_polling_threads_timers_or_network(self):
        code = SOURCE.read_text(encoding="utf-8")
        for token in ("QTimer", "Thread(", "time.sleep", "import socket",
                      "import subprocess", "asyncio", "importlib", "requests",
                      "sqlite3", "while True", "poll("):
            with self.subTest(token=token):
                self.assertNotIn(token, code)
        self.assertIn("from dataclasses import dataclass, replace", code)
        self.assertIn("from enum import Enum", code)


if __name__ == "__main__":
    unittest.main()
