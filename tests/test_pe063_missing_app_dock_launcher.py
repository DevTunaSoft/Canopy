"""PE-063: missing-app state denies dock and launcher launch intents.

The tests exercise the source contracts only; no app is launched, no QML,
asset or protected file is touched.
"""
import unittest

from canopy_features.apps.app_launch_preview import (
    REASON_INVALID_INPUT,
    STATUS_DENIED,
    STATUS_READY,
    compose_app_launch_preview,
)
from canopy_features.catalog.missing_app_availability import (
    REASON_NOT_IN_CATALOG,
    REASON_OK,
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    AppAvailability,
    MissingAppTracker,
)
from canopy_features.dock.click_intents import ClickIntent, IntentKind
from canopy_features.dock.dock_action_preview import (
    APPROVED,
    DENIED,
    REASON_APP_UNAVAILABLE,
    compose_dock_action_preview,
)
from canopy_features.dock.dock_pinned_items import PinnedItems
from canopy_features.dock.dock_running_indicators import IndicatorState
from canopy_features.dock.keyboard_navigation import DockFocusOrder

FILES = "Files"
BROWSER = "Browser"
CATALOG = (
    ("org.example.One.desktop", "One"),
    ("org.example.Two.desktop", "Two"),
)
ALLOWED = tuple(app_id for app_id, _ in CATALOG)
ENV_ALLOW = ("PATH", "LANG")
ENV_SOURCE = {"PATH": "/usr/bin", "LANG": "C.UTF-8"}


def missing(app_id="org.example.Missing.desktop"):
    return AppAvailability(app_id, STATUS_UNAVAILABLE, REASON_NOT_IN_CATALOG)


def launchable(app_id="org.example.One.desktop"):
    return AppAvailability(app_id, STATUS_AVAILABLE, REASON_OK)


def dock_inputs(kind=IntentKind.LAUNCH, reason="installed", owners=()):
    intent = ClickIntent(kind, FILES, reason)
    pinned = PinnedItems(items=(FILES, BROWSER))
    indicators = IndicatorState(sequence=7, owners=tuple(owners))
    focus = DockFocusOrder(items=[FILES, BROWSER])
    if kind is IntentKind.FOCUS:
        focus.focus(FILES)
    return intent, pinned, indicators, focus


class DockMissingAppTests(unittest.TestCase):
    def test_missing_app_denies_launch_with_no_target_or_action(self):
        inputs = dock_inputs()
        result = compose_dock_action_preview(
            *inputs, FILES, availability={"Files": missing()})
        self.assertEqual(result.status, DENIED)
        self.assertEqual(result.reason, REASON_APP_UNAVAILABLE)
        self.assertIsNone(result.target)
        self.assertIsNone(result.action)
        self.assertFalse(result.approved)
        payload = repr(result.to_dict())
        self.assertNotIn("org.example", payload)
        self.assertNotIn("Files", payload)

    def test_single_record_form_also_denies_launch(self):
        inputs = dock_inputs()
        result = compose_dock_action_preview(
            *inputs, FILES, availability=missing())
        self.assertEqual(result.status, DENIED)
        self.assertEqual(result.reason, REASON_APP_UNAVAILABLE)

    def test_available_state_preserves_existing_launch_approval(self):
        inputs = dock_inputs()
        baseline = compose_dock_action_preview(*inputs, FILES)
        with_state = compose_dock_action_preview(
            *inputs, FILES, availability={"Files": launchable()})
        self.assertEqual(with_state, baseline)
        self.assertEqual(with_state.status, APPROVED)

    def test_focus_is_not_blocked_by_missing_launch_state(self):
        inputs = dock_inputs(IntentKind.FOCUS, "running", ((42, FILES),))
        result = compose_dock_action_preview(
            *inputs, FILES, availability={"Files": missing()})
        self.assertEqual(result.status, APPROVED)
        self.assertEqual(result.action, "focus")

    def test_hostile_availability_value_fails_closed_without_crash(self):
        inputs = dock_inputs()
        for value in ({"Files": object()}, {"Files": None}, {"Files": "yes"}):
            with self.subTest(value=value):
                result = compose_dock_action_preview(
                    *inputs, FILES, availability=value)
                self.assertEqual(result.status, DENIED)
                self.assertEqual(result.reason, REASON_APP_UNAVAILABLE)

    def test_unrelated_target_is_unchanged(self):
        inputs = dock_inputs()
        result = compose_dock_action_preview(
            *inputs, FILES, availability={"Browser": missing()})
        self.assertEqual(result.status, APPROVED)


class LauncherMissingAppTests(unittest.TestCase):
    def compose(self, **options):
        merged = dict(
            allowed_app_ids=ALLOWED,
            env_allow=ENV_ALLOW,
            env_source=ENV_SOURCE,
        )
        merged.update(options)
        return compose_app_launch_preview("One", CATALOG, **merged)

    def test_missing_app_denies_ready_launch_preview(self):
        result = self.compose(availability=MissingAppTracker().state(
            "org.example.Missing.desktop"))
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, REASON_APP_UNAVAILABLE)
        self.assertFalse(result.ready)
        self.assertEqual(result.claims, ())

    def test_available_app_keeps_existing_ready_preview(self):
        baseline = self.compose()
        with_state = self.compose(availability=launchable())
        self.assertEqual(with_state, baseline)
        self.assertEqual(with_state.status, STATUS_READY)

    def test_tracker_observed_missing_state_denies_launch(self):
        tracker = MissingAppTracker()
        state = tracker.observe(
            "org.example.One.desktop", in_catalog=True,
            tryexec_ok=False, entry_readable=True)
        result = self.compose(availability=state)
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, REASON_APP_UNAVAILABLE)
        self.assertFalse(state.launch_permitted)
        self.assertFalse(result.ready)

    def test_wrong_availability_type_is_denied_without_echo(self):
        for value in (7, "unavailable", object()):
            with self.subTest(value=value):
                result = self.compose(availability=value)
                self.assertEqual(result.status, STATUS_DENIED)
                self.assertEqual(result.reason, REASON_INVALID_INPUT)
                self.assertNotIn(str(value), repr(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
