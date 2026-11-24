"""Offline unit tests for the keyboard tooltip-focus contract.

No Qt, X11, Wayland, Mint or screen-reader runtime is exercised here.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.accessibility import tooltip_focus_contract as contract


class TooltipFocusContractTests(unittest.TestCase):
    def test_pointer_hover_shows_tooltip(self):
        result = contract.describe_tooltip(
            contract.TooltipInput(hovered=True, active_focus=False),
            accessible_name="Files preview",
        )
        self.assertTrue(result.visible)
        self.assertTrue(result.via_pointer)
        self.assertFalse(result.via_keyboard)

    def test_keyboard_focus_without_hover_shows_tooltip(self):
        # Absent hover: pointer never entered the control.
        result = contract.describe_tooltip(
            contract.TooltipInput(hovered=False, active_focus=True),
            accessible_name="Files preview",
        )
        self.assertTrue(result.visible)
        self.assertTrue(result.via_keyboard)
        self.assertFalse(result.via_pointer)

    def test_focus_lost_and_hover_absent_hides_tooltip(self):
        # Focus lost: the control is neither hovered nor focused.
        result = contract.describe_tooltip(
            contract.TooltipInput(hovered=False, active_focus=False),
            accessible_name="Files preview",
        )
        self.assertFalse(result.visible)
        self.assertFalse(result.via_keyboard)
        self.assertFalse(result.via_pointer)
        self.assertFalse(contract.tooltip_visible(
            contract.TooltipInput(hovered=False, active_focus=False)))

    def test_disabled_or_empty_text_never_shows(self):
        for state in (
            contract.TooltipInput(hovered=True, active_focus=True, enabled=False),
            contract.TooltipInput(hovered=True, active_focus=True, has_text=False),
        ):
            with self.subTest(state=state):
                self.assertFalse(contract.tooltip_visible(state))
                result = contract.describe_tooltip(
                    state, accessible_name="Files preview")
                self.assertFalse(result.visible)
                self.assertFalse(result.via_keyboard)

    def test_both_hover_and_focus_report_both_triggers(self):
        result = contract.describe_tooltip(
            contract.TooltipInput(hovered=True, active_focus=True),
            accessible_name="Files preview",
        )
        self.assertTrue(result.visible)
        self.assertTrue(result.via_pointer)
        self.assertTrue(result.via_keyboard)

    def test_accessible_label_persists_when_tooltip_hidden(self):
        result = contract.describe_tooltip(
            contract.TooltipInput(hovered=False, active_focus=False),
            accessible_name="Files preview",
            accessible_description="Toggle Files preview",
        )
        self.assertFalse(result.visible)
        self.assertEqual(result.screen_reader_label,
                         "Files preview; Toggle Files preview")
        self.assertEqual(result.role, "button")

    def test_state_is_immutable_and_stateless(self):
        state = contract.TooltipInput(hovered=False, active_focus=True)
        with self.assertRaises(FrozenInstanceError):
            state.active_focus = False
        first = contract.describe_tooltip(state, accessible_name="Files")
        second = contract.describe_tooltip(state, accessible_name="Files")
        self.assertEqual(first, second)
        # A later focus-lost event is unaffected by earlier focus state.
        lost = contract.describe_tooltip(
            contract.TooltipInput(hovered=False, active_focus=False),
            accessible_name="Files")
        self.assertFalse(lost.visible)

    def test_rejects_non_bools_and_bad_text(self):
        for kwargs in ({"hovered": 1, "active_focus": True},
                       {"hovered": False, "active_focus": "yes"},
                       {"hovered": True, "active_focus": False, "enabled": 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(TypeError):
                    contract.TooltipInput(**kwargs)
        state = contract.TooltipInput(hovered=True, active_focus=False)
        for name in ("", "   ", "x" * (contract.MAX_NAME_LENGTH + 1)):
            with self.subTest(name=name[:8]):
                with self.assertRaises(ValueError):
                    contract.describe_tooltip(state, accessible_name=name)
        with self.assertRaises(ValueError):
            contract.describe_tooltip(
                state, accessible_name="Files",
                accessible_description="d" * (contract.MAX_DESCRIPTION_LENGTH + 1))
        with self.assertRaises(TypeError):
            contract.tooltip_visible(object())

    def test_contract_metadata(self):
        self.assertEqual(contract.CONTRACT_VERSION, 1)
        self.assertEqual(contract.INTENDED_QML_BINDING,
                         "ToolTip.visible: hovered || activeFocus")
        self.assertEqual(len(contract.MODELLED_QML_BINDINGS), 3)
        self.assertTrue(all(binding == "ToolTip.visible: hovered"
                            for _, binding in contract.MODELLED_QML_BINDINGS))

    def test_no_polling_services_or_network(self):
        source = Path(contract.__file__).read_text(encoding="utf-8")
        for token in ("QTimer", "time.sleep", "while True", "Thread(",
                      "asyncio", "socket", "subprocess", "import requests"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
