"""Offline tests for the composed dock-action preview.

The composer reconciles four already-tested pure state models into one
immutable, auditable host decision. No process, filesystem walk, geometry,
QML or visual change is involved.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.dock.click_intents import ClickIntent, IntentKind
from canopy_features.dock.dock_pinned_items import PinnedItems
from canopy_features.dock.dock_running_indicators import IndicatorState
from canopy_features.dock.keyboard_navigation import DockFocusOrder
from canopy_features.dock.dock_action_preview import (
    APPROVED,
    DENIED,
    REASON_ALREADY_RUNNING,
    REASON_FOCUS_MISMATCH,
    REASON_INTENT_IGNORED,
    REASON_INTENT_REJECTED,
    REASON_INVALID_INDICATORS,
    REASON_INVALID_PINNED,
    REASON_INVALID_TARGET,
    REASON_NOT_IN_FOCUS_ORDER,
    REASON_NOT_PINNED,
    REASON_NOT_RUNNING,
    REASON_OK,
    REASON_TARGET_MISMATCH,
    DockActionPreview,
    PreviewInputError,
    compose_dock_action_preview,
)

MODULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "canopy_features" / "dock" / "dock_action_preview.py"
)

FILES = "Files"
BROWSER = "Browser"
MAIL = "Mail"


def make_intent(kind=IntentKind.LAUNCH, name=FILES, reason="installed"):
    return ClickIntent(kind, name, reason)


def make_pinned(*items):
    return PinnedItems(items=tuple(items) if items else (FILES, BROWSER))


def make_indicators(*owners, sequence=7):
    return IndicatorState(sequence=sequence, owners=tuple(owners))


def make_focus(*items, focused=FILES):
    order = DockFocusOrder(items=list(items) if items else [FILES, BROWSER])
    if focused is not None:
        order.focus(focused)
    return order


def compose(intent=None, pinned=None, indicators=None, focus=None, target=FILES):
    return compose_dock_action_preview(
        intent if intent is not None else make_intent(),
        pinned if pinned is not None else make_pinned(),
        indicators if indicators is not None else make_indicators(),
        focus if focus is not None else make_focus(),
        target,
    )


class DockActionPreviewApprovalTests(unittest.TestCase):
    def test_launch_approved_when_all_sources_agree(self):
        preview = compose()
        self.assertIsInstance(preview, DockActionPreview)
        self.assertEqual(preview.status, APPROVED)
        self.assertEqual(preview.reason, REASON_OK)
        self.assertTrue(preview.approved)
        self.assertEqual(preview.action, "launch")
        self.assertEqual(preview.target, FILES)
        self.assertEqual(preview.pinned_index, 0)
        self.assertEqual(preview.running_pids, 0)
        self.assertEqual(preview.intent_reason, "installed")
        self.assertEqual(preview.indicator_sequence, 7)
        self.assertTrue(preview.focus_was_on_target)

    def test_focus_approved_with_running_target(self):
        preview = compose(
            intent=make_intent(IntentKind.FOCUS, FILES, "running"),
            indicators=make_indicators((101, FILES), (102, BROWSER)),
        )
        self.assertEqual(preview.status, APPROVED)
        self.assertEqual(preview.action, "focus")
        self.assertEqual(preview.running_pids, 1)
        self.assertEqual(preview.pinned_index, 0)

    def test_pinned_index_reflects_position(self):
        preview = compose(pinned=make_pinned(BROWSER, MAIL, FILES))
        self.assertEqual(preview.pinned_index, 2)

    def test_focus_none_is_allowed_for_pointer_activation(self):
        preview = compose(focus=make_focus(focused=None))
        self.assertEqual(preview.status, APPROVED)
        self.assertFalse(preview.focus_was_on_target)

    def test_focus_on_target_records_true(self):
        preview = compose(focus=make_focus(FILES, BROWSER, focused=FILES))
        self.assertTrue(preview.focus_was_on_target)

    def test_approved_to_dict_is_bounded_mapping(self):
        data = compose().to_dict()
        self.assertEqual(set(data), {
            "status", "reason", "action", "target", "pinned_index",
            "running_pids", "intent_reason", "indicator_sequence",
            "focus_was_on_target",
        })
        self.assertEqual(data["status"], APPROVED)
        self.assertEqual(data["target"], FILES)
        self.assertEqual(data["action"], "launch")

    def test_preview_is_immutable(self):
        preview = compose()
        with self.assertRaises(FrozenInstanceError):
            preview.status = DENIED


class DockActionPreviewDenialTests(unittest.TestCase):
    def assert_denied(self, preview, reason):
        self.assertIsInstance(preview, DockActionPreview)
        self.assertEqual(preview.status, DENIED)
        self.assertEqual(preview.reason, reason)
        self.assertFalse(preview.approved)
        self.assertIsNone(preview.action)
        self.assertIsNone(preview.target)
        self.assertIsNone(preview.pinned_index)
        self.assertIsNone(preview.running_pids)
        self.assertIsNone(preview.indicator_sequence)
        self.assertIsNone(preview.intent_reason)

    def test_unapproved_target_label_denied(self):
        self.assert_denied(compose(target="NotAnApprovedDockLabel"),
                           REASON_INVALID_TARGET)

    def test_target_mismatch_denied(self):
        self.assert_denied(
            compose(intent=make_intent(IntentKind.LAUNCH, BROWSER),
                    target=FILES),
            REASON_TARGET_MISMATCH,
        )

    def test_rejected_intent_denied(self):
        self.assert_denied(
            compose(intent=make_intent(IntentKind.REJECT, "", "untrusted-id")),
            REASON_INTENT_REJECTED,
        )

    def test_ignored_intent_denied(self):
        self.assert_denied(
            compose(intent=make_intent(IntentKind.IGNORE, FILES,
                                       "launch-pending")),
            REASON_INTENT_IGNORED,
        )

    def test_not_pinned_denied(self):
        self.assert_denied(compose(pinned=make_pinned(BROWSER, MAIL)),
                           REASON_NOT_PINNED)

    def test_not_in_focus_order_denied(self):
        self.assert_denied(compose(focus=make_focus(BROWSER, MAIL,
                                                   focused=BROWSER)),
                           REASON_NOT_IN_FOCUS_ORDER)

    def test_focus_on_other_tile_denied(self):
        self.assert_denied(compose(focus=make_focus(FILES, BROWSER,
                                                   focused=BROWSER)),
                           REASON_FOCUS_MISMATCH)

    def test_launch_with_running_target_denied(self):
        self.assert_denied(
            compose(indicators=make_indicators((101, FILES))),
            REASON_ALREADY_RUNNING,
        )

    def test_focus_without_running_target_denied(self):
        self.assert_denied(
            compose(intent=make_intent(IntentKind.FOCUS, FILES, "running")),
            REASON_NOT_RUNNING,
        )

    def test_malformed_pinned_items_denied_not_raised(self):
        self.assert_denied(
            compose(pinned=PinnedItems(items=("Files", 42))),
            REASON_INVALID_PINNED,
        )

    def test_malformed_indicator_owners_denied_not_raised(self):
        self.assert_denied(
            compose(indicators=IndicatorState(sequence=3,
                                              owners=((101, FILES, 9),))),
            REASON_INVALID_INDICATORS,
        )

    def test_boolean_indicator_sequence_denied(self):
        self.assert_denied(
            compose(indicators=IndicatorState(sequence=True, owners=())),
            REASON_INVALID_INDICATORS,
        )

    def test_denial_to_dict_carries_no_source_fields(self):
        data = compose(pinned=make_pinned(BROWSER)).to_dict()
        for field in ("action", "target", "pinned_index", "running_pids",
                      "intent_reason", "indicator_sequence"):
            self.assertIsNone(data[field])
        self.assertEqual(data["reason"], REASON_NOT_PINNED)


class DockActionPreviewTypeTests(unittest.TestCase):
    def test_wrong_intent_type_raises(self):
        with self.assertRaises(PreviewInputError):
            compose(intent=object())

    def test_wrong_pinned_type_raises(self):
        with self.assertRaises(PreviewInputError):
            compose(pinned=object())

    def test_wrong_indicators_type_raises(self):
        with self.assertRaises(PreviewInputError):
            compose(indicators=object())

    def test_wrong_focus_type_raises(self):
        with self.assertRaises(PreviewInputError):
            compose(focus=object())

    def test_non_string_target_raises(self):
        for bad in (None, 1, 3.5, True, (), [], {}):
            with self.subTest(bad=bad):
                with self.assertRaises(PreviewInputError):
                    compose(target=bad)

    def test_reason_codes_are_stable_tokens(self):
        self.assertEqual(REASON_OK, "ok")
        self.assertEqual(REASON_INVALID_TARGET, "invalid_target")
        self.assertEqual(REASON_ALREADY_RUNNING, "already_running")

    def test_module_is_inert_data_only(self):
        source = MODULE_SOURCE.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess", "Popen", "os.system", "os.startfile",
            "QDesktopServices", "QProcess", "socket", "requests",
            "QTimer", "Thread(", "asyncio", "time.sleep", "while True",
            "open(", "Path(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
