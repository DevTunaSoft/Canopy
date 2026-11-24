"""Tests for the pure no-echo focus-announcement record.

Run: python -m unittest tests.test_c100_launcher_focus_announcement -v
No Qt runtime, screen reader, window manager, process launch or I/O is involved.
"""
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.dock.keyboard_navigation import FocusTransition
from canopy_features.launcher import focus_announcement as announcement_mod
from canopy_features.launcher.app_search_casefold import EXACT, Match
from canopy_features.launcher.focus_announcement import (
    CLAIM_NO_APP_IDS_ECHOED,
    CLAIM_NO_LABELS_ECHOED,
    CLAIM_NO_TARGET_TEXT_ECHOED,
    CLAIM_NO_WINDOW_IDS_ECHOED,
    FIXED_CLAIMS,
    MAX_DURATION_MS,
    REASON_NO_FOCUS,
    REASON_NO_MOTION,
    REASON_OK,
    STATUS_ANNOUNCE,
    STATUS_SILENT,
    TOKEN_ACTION_READY,
    TOKEN_FOCUS_MOVED,
    TOKEN_FOCUS_UNCHANGED,
    TOKEN_FOCUS_WRAPPED,
    TOKEN_NO_RESULTS,
    TOKEN_NO_SURFACE,
    TOKEN_REDUCED_MOTION,
    TOKEN_RESULT_FOCUSED,
    TOKEN_SURFACE_DOCK,
    AnnouncementInputError,
    compose_focus_announcement,
)
from canopy_features.launcher.launcher_keyboard_navigation import NO_FOCUS
from canopy_features.launcher.launcher_search_view import (
    STATUS_EMPTY,
    STATUS_READY,
    SearchView,
)
from canopy_features.launcher.shell_action_decision import (
    REASON_OK as DECISION_REASON_OK,
    STATUS_READY as DECISION_READY,
    SURFACE_DOCK,
    ShellActionDecision,
)


def view():
    return SearchView("fire", (Match("Firefox", EXACT, 0),),
                      0, "Firefox", STATUS_READY)


def transition():
    return FocusTransition("SECRET-OLD-ID", "SECRET-NEW-ID",
                           moved=True, wrapped=False, duration_ms=120)


def decision():
    return ShellActionDecision(DECISION_READY, DECISION_REASON_OK,
                               SURFACE_DOCK, "launch", "SECRET-TARGET")


def compose(t=None, v=None, d=None, **kwargs):
    return compose_focus_announcement(
        transition() if t is None else t,
        view() if v is None else v,
        decision() if d is None else d,
        **kwargs)


class AnnouncementTests(unittest.TestCase):
    def test_fixed_claims(self):
        for claim in (CLAIM_NO_WINDOW_IDS_ECHOED, CLAIM_NO_APP_IDS_ECHOED,
                      CLAIM_NO_LABELS_ECHOED, CLAIM_NO_TARGET_TEXT_ECHOED):
            with self.subTest(claim=claim):
                self.assertIn(claim, FIXED_CLAIMS)
        self.assertEqual(STATUS_ANNOUNCE, "ANNOUNCE")
        self.assertEqual(STATUS_SILENT, "SILENT")
        self.assertEqual(REASON_OK, "ok")

    def test_moved_focus_announces_fixed_tokens(self):
        result = compose()
        self.assertEqual(result.status, STATUS_ANNOUNCE)
        self.assertEqual(result.reason, REASON_OK)
        self.assertIn(TOKEN_FOCUS_MOVED, result.tokens)
        self.assertIn(TOKEN_RESULT_FOCUSED, result.tokens)
        self.assertIn(TOKEN_SURFACE_DOCK, result.tokens)
        self.assertIn(TOKEN_ACTION_READY, result.tokens)
        self.assertEqual(result.result_count, 1)

    def test_no_source_text_is_echoed(self):
        payload = repr(compose().to_dict())
        for secret in ("SECRET-OLD-ID", "SECRET-NEW-ID", "SECRET-TARGET",
                       "Firefox", "fire"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, payload)

    def test_unmoved_focus_is_silent(self):
        unchanged = FocusTransition("a", "a", moved=False,
                                    wrapped=False, duration_ms=0)
        result = compose(t=unchanged)
        self.assertEqual(result.status, STATUS_SILENT)
        self.assertEqual(result.reason, REASON_NO_MOTION)
        self.assertIn(TOKEN_FOCUS_UNCHANGED, result.tokens)

    def test_wrapped_and_reduced_motion_tokens(self):
        wrapped = FocusTransition("a", "b", moved=True,
                                  wrapped=True, duration_ms=0)
        result = compose(t=wrapped)
        self.assertIn(TOKEN_FOCUS_WRAPPED, result.tokens)
        self.assertIn(TOKEN_REDUCED_MOTION, result.tokens)

    def test_empty_search_announces_no_results(self):
        empty = SearchView("", (), NO_FOCUS, None, STATUS_EMPTY)
        result = compose(v=empty)
        self.assertIn(TOKEN_NO_RESULTS, result.tokens)
        self.assertEqual(result.result_count, 0)
        self.assertEqual(result.focus_position, -1)

    def test_idle_decision_has_no_surface_or_action_tokens(self):
        idle = ShellActionDecision("IDLE", "no_action")
        result = compose(d=idle)
        self.assertIn(TOKEN_NO_SURFACE, result.tokens)
        self.assertNotIn(TOKEN_ACTION_READY, result.tokens)

    def test_tokens_are_sorted_unique_fixed_strings(self):
        tokens = compose().tokens
        self.assertIsInstance(tokens, tuple)
        self.assertEqual(tokens, tuple(sorted(set(tokens))))
        self.assertTrue(all(type(token) is str for token in tokens))

    def test_to_dict_shape(self):
        self.assertEqual(set(compose().to_dict()), {
            "status", "reason", "tokens", "result_count",
            "focus_position", "claims"})

    def test_record_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            compose().result_count = 99

    def test_deterministic(self):
        self.assertEqual(compose(), compose())

    def test_module_has_no_io_or_process_api(self):
        with open(announcement_mod.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for token in ("subprocess", "Popen", "os.system", "open(", "Path("):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class FailClosedTests(unittest.TestCase):
    def test_wrong_source_types_rejected(self):
        for args in ((7, view(), decision()),
                     (transition(), 7, decision()),
                     (transition(), view(), 7)):
            with self.subTest(args=args):
                with self.assertRaises(AnnouncementInputError):
                    compose_focus_announcement(*args)

    def test_bad_transition_fields_rejected(self):
        for bad in (True, -1, MAX_DURATION_MS + 1, "120"):
            with self.subTest(bad=bad):
                with self.assertRaises(AnnouncementInputError):
                    compose(t=FocusTransition("a", "b", True, False, bad))

    def test_invalid_view_state_rejected(self):
        bad = SearchView("fire", (Match("Firefox", EXACT, 0),),
                         7, "Firefox", STATUS_READY)
        with self.assertRaises(AnnouncementInputError):
            compose(v=bad)

    def test_empty_view_with_focus_index_rejected(self):
        bad = SearchView("", (), 0, None, STATUS_EMPTY)
        with self.assertRaises(AnnouncementInputError):
            compose(v=bad)

    def test_unknown_decision_status_rejected(self):
        bad = ShellActionDecision("UNKNOWN", "unknown")
        with self.assertRaises(AnnouncementInputError):
            compose(d=bad)

    def test_focus_without_target_is_silent(self):
        no_target = FocusTransition("a", None, moved=True,
                                    wrapped=False, duration_ms=120)
        result = compose(t=no_target)
        self.assertEqual(result.status, STATUS_SILENT)
        self.assertEqual(result.reason, REASON_NO_FOCUS)


if __name__ == "__main__":
    unittest.main()
