"""Tests for the pure, no-echo dock presentation intent snapshot.

Run: python -m unittest tests.test_c100_dock_presentation_intent -v
No Qt runtime, window manager, geometry, D-Bus or desktop is involved.
"""
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from canopy_features.dock import dock_presentation_intent as preview_mod
from canopy_features.dock.dock_presentation_intent import (
    FIXED_CLAIMS,
    REASON_INTENT_DISAGREEMENT,
    REASON_INVALID_INPUT,
    REASON_OK,
    REASON_UNTRUSTED_SURFACE,
    STATUS_DENIED,
    STATUS_READY,
    DockPresentationIntent,
    compose_dock_presentation_intent,
)
from canopy_features.dock.click_intents import ClickIntent, IntentKind
from canopy_features.dock.dock_running_indicators import (
    AppStarted,
    apply_events,
    empty_state,
)
from canopy_features.dock.notification_badges import NotificationBadges


def indicators(*pairs):
    events = tuple(AppStarted(sequence=index + 1, app_id=app, pid=pid)
                   for index, (app, pid) in enumerate(pairs))
    return apply_events(empty_state(), events)


def badges(*counts):
    store = NotificationBadges(tuple(app for app, _ in counts))
    for app, count in counts:
        store.set(app, count)
    return store


IND = indicators(("Files", 101), ("Files", 102), ("Browser", 201))
BADGES = badges(("Files", 3))
FOCUS = ClickIntent(IntentKind.FOCUS, "Files", "running")


def compose(intent=FOCUS, ind=IND, badge_store=BADGES):
    return compose_dock_presentation_intent(intent, ind, badge_store)


class ApprovedTests(unittest.TestCase):
    def test_constants_are_fixed_negative_claims(self):
        self.assertEqual(STATUS_READY, "READY")
        self.assertEqual(STATUS_DENIED, "DENIED")
        self.assertEqual(REASON_OK, "ok")
        self.assertIsInstance(FIXED_CLAIMS, tuple)
        self.assertTrue(FIXED_CLAIMS)
        self.assertTrue(all(type(c) is str for c in FIXED_CLAIMS))
        for claim in ("no_pids_echoed", "no_app_ids_echoed", "no_labels_echoed",
                      "no_geometry_read", "no_process_launched", "no_value_echo"):
            with self.subTest(claim=claim):
                self.assertIn(claim, FIXED_CLAIMS)

    def test_approved_counts_only(self):
        result = compose()
        self.assertEqual(result, DockPresentationIntent(
            STATUS_READY, REASON_OK, running_tiles=2, badge_tiles=1,
            total_pids=3, claims=FIXED_CLAIMS))
        self.assertTrue(result.ready)

    def test_no_pids_app_ids_or_labels_are_echoed(self):
        payload = repr(compose().to_dict())
        for secret in ("101", "102", "201", "Files", "Browser"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, payload)

    def test_empty_state_is_approved_with_zero_counts(self):
        result = compose(
            ClickIntent(IntentKind.REJECT, "", "untrusted-id"),
            empty_state(), NotificationBadges(()))
        self.assertEqual(result.running_tiles, 0)
        self.assertEqual(result.badge_tiles, 0)
        self.assertEqual(result.total_pids, 0)
        self.assertEqual(result.claims, FIXED_CLAIMS)

    def test_to_dict_shape(self):
        self.assertEqual(set(compose().to_dict()), {
            "status", "reason", "running_tiles", "badge_tiles",
            "total_pids", "claims"})

    def test_record_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            compose().running_tiles = 99

    def test_no_geometry_or_process_spawner_import(self):
        with open(preview_mod.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("display_geometry", source)
        self.assertNotIn("subprocess", source)


class DenialTests(unittest.TestCase):
    def assert_terse_denial(self, result, reason):
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, reason)
        self.assertFalse(result.ready)
        self.assertEqual(result.running_tiles, 0)
        self.assertEqual(result.badge_tiles, 0)
        self.assertEqual(result.total_pids, 0)
        self.assertEqual(result.claims, ())

    def test_focus_on_non_running_tile_disagrees(self):
        result = compose(ClickIntent(IntentKind.FOCUS, "Mail", "running"))
        self.assert_terse_denial(result, REASON_INTENT_DISAGREEMENT)

    def test_launch_of_running_tile_disagrees(self):
        result = compose(ClickIntent(IntentKind.LAUNCH, "Files", "installed"))
        self.assert_terse_denial(result, REASON_INTENT_DISAGREEMENT)

    def test_untrusted_running_app_is_denied_without_echo(self):
        result = compose(FOCUS, indicators(("SECRET-APP", 424242)), BADGES)
        self.assert_terse_denial(result, REASON_UNTRUSTED_SURFACE)
        self.assertNotIn("SECRET-APP", repr(result.to_dict()))
        self.assertNotIn("424242", repr(result.to_dict()))

    def test_untrusted_badge_app_is_denied_without_echo(self):
        result = compose(FOCUS, IND, badges(("SECRET-APP", 7)))
        self.assert_terse_denial(result, REASON_UNTRUSTED_SURFACE)
        self.assertNotIn("SECRET-APP", repr(result.to_dict()))

    def test_wrong_source_types_are_denied(self):
        for args in ((7, IND, BADGES), (FOCUS, {}, BADGES), (FOCUS, IND, ())):
            with self.subTest(args=args):
                self.assert_terse_denial(
                    compose_dock_presentation_intent(*args), REASON_INVALID_INPUT)

    def test_fault_injected_ids_are_not_echoed(self):
        with patch.object(preview_mod, "indicator_ids",
                          return_value=("SECRET-INJECTED",)):
            result = compose()
        self.assert_terse_denial(result, REASON_UNTRUSTED_SURFACE)
        self.assertNotIn("SECRET-INJECTED", repr(result.to_dict()))


class HostileLabelTests(unittest.TestCase):
    """A name that is not an exact str must never produce a presentation claim.

    ``ClickIntent`` is a frozen dataclass but its fields are not type-checked at
    construction. A bounded hostile label (list, dict, int or a str subclass
    with no hash) is still a caller-supplied value at this composition seam, so
    the seam must fail closed with the module's denial record, never with a
    raw built-in exception and never with a READY claim.
    """

    def assert_malformed_name_denied(self, result):
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, REASON_INVALID_INPUT)
        self.assertFalse(result.ready)
        self.assertEqual(result.running_tiles, 0)
        self.assertEqual(result.badge_tiles, 0)
        self.assertEqual(result.total_pids, 0)
        self.assertEqual(result.claims, ())
        self.assertNotIn("Files", repr(result.to_dict()))

    def test_unhashable_actionable_name_denies_without_exception(self):
        for kind in (IntentKind.FOCUS, IntentKind.LAUNCH):
            with self.subTest(kind=kind):
                result = compose_dock_presentation_intent(
                    ClickIntent(kind, ["Files"], "running"), IND, BADGES)
                self.assert_malformed_name_denied(result)

    def test_non_string_inert_name_never_claims_ready(self):
        for kind in (IntentKind.REJECT, IntentKind.IGNORE):
            for name in ({"app": "Files"}, 7, ("Files",)):
                with self.subTest(kind=kind, name=type(name).__name__):
                    result = compose_dock_presentation_intent(
                        ClickIntent(kind, name, "untrusted-id"), IND, BADGES)
                    self.assert_malformed_name_denied(result)

    def test_unhashable_str_subclass_name_denies_without_exception(self):
        class UnhashableLabel(str):
            __hash__ = None

        result = compose_dock_presentation_intent(
            ClickIntent(IntentKind.FOCUS, UnhashableLabel("Files"), "running"),
            IND, BADGES)
        self.assert_malformed_name_denied(result)


if __name__ == "__main__":
    unittest.main()
