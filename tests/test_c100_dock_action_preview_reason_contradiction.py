"""Regression tests for contradictory dock-action intent reason flags.

The click mapper emits a reason that belongs to exactly one action kind.
A host-supplied intent whose action and reason disagree must not become a
false APPROVED preview; malformed reason containers must not raise raw
exceptions. Pure data only: no process, I/O, geometry or visual change.
"""
import unittest

from canopy_features.dock.click_intents import ClickIntent, IntentKind
from canopy_features.dock.dock_pinned_items import PinnedItems
from canopy_features.dock.dock_running_indicators import IndicatorState
from canopy_features.dock.keyboard_navigation import DockFocusOrder
from canopy_features.dock.dock_action_preview import (
    APPROVED,
    DENIED,
    REASON_INVALID_INPUT,
    REASON_OK,
    compose_dock_action_preview,
)

FILES = "Files"
BROWSER = "Browser"


def compose(intent, *, running=True):
    focus = DockFocusOrder(items=[FILES, BROWSER])
    focus.focus(FILES)
    owners = ((101, FILES),) if running else ()
    return compose_dock_action_preview(
        intent,
        PinnedItems(items=(FILES, BROWSER)),
        IndicatorState(sequence=7, owners=owners),
        focus,
        FILES,
    )


def assert_denied_invalid(test, preview):
    test.assertEqual(preview.status, DENIED)
    test.assertEqual(preview.reason, REASON_INVALID_INPUT)
    test.assertIsNone(preview.action)
    test.assertIsNone(preview.target)
    test.assertIsNone(preview.intent_reason)


class DockActionPreviewReasonContradictionTests(unittest.TestCase):
    def test_launch_action_with_focus_reason_denied(self):
        preview = compose(ClickIntent(IntentKind.LAUNCH, FILES, "running"),
                          running=False)
        assert_denied_invalid(self, preview)

    def test_focus_action_with_launch_reason_denied(self):
        preview = compose(ClickIntent(IntentKind.FOCUS, FILES, "installed"))
        assert_denied_invalid(self, preview)

    def test_launch_action_with_ignore_reason_denied(self):
        preview = compose(ClickIntent(IntentKind.LAUNCH, FILES, "launch-pending"),
                          running=False)
        assert_denied_invalid(self, preview)

    def test_focus_action_with_missing_target_reason_denied(self):
        preview = compose(ClickIntent(IntentKind.FOCUS, FILES, "missing-target"))
        assert_denied_invalid(self, preview)

    def test_launch_action_with_reject_reason_denied(self):
        preview = compose(ClickIntent(IntentKind.LAUNCH, FILES, "untrusted-id"),
                          running=False)
        assert_denied_invalid(self, preview)

    def test_unhashable_reason_container_denied(self):
        for bad in (["installed"], {"reason": "installed"}, {1, 2}):
            with self.subTest(bad=bad):
                preview = compose(
                    ClickIntent(IntentKind.LAUNCH, FILES, bad),  # type: ignore[arg-type]
                    running=False,
                )
                assert_denied_invalid(self, preview)

    def test_matching_reason_pairs_remain_approved(self):
        launch = compose(ClickIntent(IntentKind.LAUNCH, FILES, "installed"),
                         running=False)
        self.assertEqual(launch.status, APPROVED)
        self.assertEqual(launch.reason, REASON_OK)
        self.assertEqual(launch.intent_reason, "installed")
        focus = compose(ClickIntent(IntentKind.FOCUS, FILES, "running"))
        self.assertEqual(focus.status, APPROVED)
        self.assertEqual(focus.reason, REASON_OK)
        self.assertEqual(focus.intent_reason, "running")


if __name__ == "__main__":
    unittest.main()
