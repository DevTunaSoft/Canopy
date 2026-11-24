"""Regression tests for duplicate pinned IDs in the dock-action preview.

The pinned snapshot describes dock tile identity. A repeated app ID makes the
preview's ``pinned_index`` ambiguous: two tiles answer to the same label, so
an APPROVED record would claim a unique actionable tile that does not exist.
The composer must fail closed with the existing invalid_pinned denial and no
source fields. Pure data only: no process, I/O, geometry or visual change.
"""
import unittest

from canopy_features.dock.click_intents import ClickIntent, IntentKind
from canopy_features.dock.dock_pinned_items import PinnedItems
from canopy_features.dock.dock_running_indicators import IndicatorState
from canopy_features.dock.keyboard_navigation import DockFocusOrder
from canopy_features.dock.dock_action_preview import (
    APPROVED,
    DENIED,
    REASON_INVALID_PINNED,
    REASON_NOT_PINNED,
    REASON_OK,
    DockActionPreview,
    compose_dock_action_preview,
)

FILES = "Files"
BROWSER = "Browser"


def compose(pinned_items, *, kind=IntentKind.LAUNCH, reason="installed",
            running=()):
    focus = DockFocusOrder(items=[FILES, BROWSER])
    focus.focus(FILES)
    return compose_dock_action_preview(
        ClickIntent(kind, FILES, reason),
        PinnedItems(items=pinned_items),
        IndicatorState(sequence=7, owners=tuple(running)),
        focus,
        FILES,
    )


class DuplicatePinnedIdTests(unittest.TestCase):
    def assert_invalid_pinned(self, preview):
        self.assertIsInstance(preview, DockActionPreview)
        self.assertEqual(preview.status, DENIED)
        self.assertEqual(preview.reason, REASON_INVALID_PINNED)
        self.assertIsNone(preview.action)
        self.assertIsNone(preview.target)
        self.assertIsNone(preview.pinned_index)
        self.assertIsNone(preview.running_pids)
        self.assertIsNone(preview.intent_reason)
        self.assertIsNone(preview.indicator_sequence)
        self.assertFalse(preview.focus_was_on_target)

    def test_duplicate_target_pin_denied(self):
        self.assert_invalid_pinned(compose((FILES, FILES)))

    def test_triple_target_pin_denied(self):
        self.assert_invalid_pinned(compose((FILES, FILES, FILES)))

    def test_duplicate_other_pin_denied(self):
        self.assert_invalid_pinned(compose((BROWSER, FILES, FILES)))

    def test_duplicate_pin_denied_for_focus_intent(self):
        self.assert_invalid_pinned(
            compose((FILES, FILES), kind=IntentKind.FOCUS, reason="running",
                    running=((101, FILES),))
        )

    def test_duplicate_and_malformed_pin_denied(self):
        self.assert_invalid_pinned(compose((FILES, FILES, 42)))

    def test_unique_reordered_pins_still_approved(self):
        preview = compose((BROWSER, FILES))
        self.assertEqual(preview.status, APPROVED)
        self.assertEqual(preview.reason, REASON_OK)
        self.assertEqual(preview.pinned_index, 1)
        self.assertEqual(preview.target, FILES)

    def test_unique_pins_without_target_still_not_pinned(self):
        preview = compose((BROWSER,))
        self.assertEqual(preview.status, DENIED)
        self.assertEqual(preview.reason, REASON_NOT_PINNED)


if __name__ == "__main__":
    unittest.main()
