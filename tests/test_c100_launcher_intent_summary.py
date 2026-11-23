"""Offline unit tests for the composed launcher intent summary.

Verifies that search ranking, visible favorites and a shell-free, allowlisted
argv are composed into one deterministic, immutable host decision record.
No Qt, desktop database, process launch or desktop claim is involved.
"""
import json
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.launcher.launcher_intent_summary import (
    MAX_CATALOG_ENTRIES,
    MAX_FAVORITES,
    MAX_QUERY_CHARS,
    STATUS_NO_MATCH,
    STATUS_NOT_APPROVED,
    STATUS_READY,
    LauncherIntentError,
    LauncherIntentSummary,
    summarize_launcher_intent,
)


CATALOG = (
    ("org.mozilla.firefox.desktop", "Firefox"),
    ("org.gnome.Nautilus.desktop", "Files"),
    ("org.kde.konsole.desktop", "Konsole"),
    ("org.gimp.GIMP.desktop", "GNU Image Manipulation Program"),
)


class LauncherIntentSummaryTests(unittest.TestCase):
    def test_exact_query_selects_match_with_shell_free_argv(self):
        result = summarize_launcher_intent(
            "firefox", CATALOG,
            allowed_app_ids={"org.mozilla.firefox.desktop"},
        )
        self.assertEqual(result.status, STATUS_READY)
        self.assertEqual(result.selected_app_id, "org.mozilla.firefox.desktop")
        self.assertEqual(
            result.argv,
            ("gio", "launch", "--", "org.mozilla.firefox.desktop"),
        )
        self.assertEqual(result.matches[0].name, "Firefox")
        self.assertEqual(result.matches[0].tier, "exact")

    def test_allowlist_rejection_is_fail_closed_with_empty_argv(self):
        result = summarize_launcher_intent(
            "firefox", CATALOG,
            allowed_app_ids={"org.gnome.Nautilus.desktop"},
        )
        self.assertEqual(result.status, STATUS_NOT_APPROVED)
        self.assertEqual(result.argv, ())
        self.assertEqual(result.selected_app_id, "org.mozilla.firefox.desktop")

    def test_blank_query_prefers_first_visible_favorite(self):
        result = summarize_launcher_intent(
            "   ", CATALOG,
            favorites=("org.kde.konsole.desktop", "org.mozilla.firefox.desktop"),
        )
        self.assertEqual(result.selected_app_id, "org.kde.konsole.desktop")
        self.assertEqual(result.status, STATUS_READY)
        self.assertTrue(all(match.tier == "all" for match in result.matches))

    def test_blank_query_without_favorites_selects_first_catalog_entry(self):
        result = summarize_launcher_intent("", CATALOG)
        self.assertEqual(result.selected_app_id, "org.mozilla.firefox.desktop")

    def test_no_match_reports_no_match_and_no_argv(self):
        result = summarize_launcher_intent("zzzzqqq", CATALOG)
        self.assertEqual(result.status, STATUS_NO_MATCH)
        self.assertEqual(result.matches, ())
        self.assertEqual(result.selected_app_id, None)
        self.assertEqual(result.argv, ())

    def test_favorites_hide_uninstalled_ids_non_destructively(self):
        result = summarize_launcher_intent(
            "", CATALOG,
            favorites=("gone.desktop", "org.kde.konsole.desktop"),
        )
        self.assertEqual(result.favorites, ("org.kde.konsole.desktop",))

    def test_favorites_are_deduplicated(self):
        ids = tuple("app%02d.desktop" % i for i in range(MAX_FAVORITES))
        catalog = tuple((app_id, "App %02d" % i) for i, app_id in enumerate(ids))
        result = summarize_launcher_intent(
            "", catalog, favorites=ids + (ids[0], "not-installed.desktop"))
        self.assertEqual(result.favorites, ids)

    def test_favorites_are_bounded(self):
        ids = tuple("app%02d.desktop" % i for i in range(MAX_FAVORITES + 1))
        catalog = tuple((app_id, "App %02d" % i) for i, app_id in enumerate(ids))
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("", catalog, favorites=ids)

    def test_duplicate_catalog_app_id_is_rejected(self):
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("fire", CATALOG + (CATALOG[0],))

    def test_malformed_app_id_is_rejected_fail_closed(self):
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("x", (("firefox;rm -rf /.desktop", "Firefox"),))

    def test_wrong_types_are_rejected(self):
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent(123, CATALOG)
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("fire", "not-a-catalog")
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("fire", CATALOG, favorites="org.kde.konsole.desktop")

    def test_oversized_inputs_are_rejected(self):
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("a" * (MAX_QUERY_CHARS + 1), CATALOG)
        too_many = tuple(
            ("app%04d.desktop" % i, "App %d" % i) for i in range(MAX_CATALOG_ENTRIES + 1)
        )
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("app", too_many)

    def test_unicode_casefold_query_matches(self):
        result = summarize_launcher_intent(
            "  GIMP  ", CATALOG,
            allowed_app_ids={"org.gimp.GIMP.desktop"},
        )
        self.assertEqual(result.selected_app_id, "org.gimp.GIMP.desktop")
        self.assertEqual(result.status, STATUS_READY)

    def test_result_is_immutable_and_json_serializable(self):
        result = summarize_launcher_intent("fire", CATALOG)
        with self.assertRaises(FrozenInstanceError):
            result.status = STATUS_NO_MATCH
        payload = result.to_dict()
        self.assertEqual(json.loads(json.dumps(payload)), payload)
        self.assertEqual(payload["argv"], list(result.argv))

    def test_deterministic_across_repeated_calls(self):
        first = summarize_launcher_intent("g", CATALOG,
                                          favorites=("org.kde.konsole.desktop",))
        second = summarize_launcher_intent("g", CATALOG,
                                           favorites=("org.kde.konsole.desktop",))
        self.assertEqual(first, second)

    def test_title_never_becomes_an_argv_token(self):
        hostile = (("safe.desktop", "Firefox $(rm -rf /); `id`"),)
        result = summarize_launcher_intent("firefox", hostile)
        self.assertEqual(result.status, STATUS_READY)
        self.assertEqual(result.matches[0].name, "Firefox $(rm -rf /); `id`")
        self.assertEqual(result.argv, ("gio", "launch", "--", "safe.desktop"))
        for token in result.argv:
            self.assertNotIn("rm -rf", token)
            self.assertNotIn("$(", token)


if __name__ == "__main__":
    unittest.main()
