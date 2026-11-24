"""Tests for the bounded favorites-aware launcher result projection.

Pure host-facing composition of app_search_casefold ranking and
launcher_favorites id validation. No Qt, no process launch, no I/O.
"""
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from canopy_features.launcher.app_search_casefold import (
    ANY,
    EXACT,
    MAX_CANDIDATES,
    MAX_QUERY_CHARS,
    MAX_RESULTS,
    PREFIX,
    Match,
)
from canopy_features.launcher import launcher_favorites_projection as proj


CATALOG = (
    ("org.mozilla.firefox", "Firefox"),
    ("org.gnome.Terminal", "Terminal"),
    ("org.gnome.Nautilus", "Files"),
    ("org.example.Firebird", "Firebird"),
    ("org.example.Chronicle", "Chronicle"),
)


class ProjectionBasicTests(unittest.TestCase):
    def test_ranked_projection_order_and_scores(self):
        view = proj.project_results("fire", CATALOG)
        self.assertEqual(view.status, proj.STATUS_READY)
        self.assertEqual(view.key, "fire")
        self.assertEqual([r.title for r in view.rows],
                         ["Firefox", "Firebird"])
        self.assertEqual([r.score for r in view.rows], [PREFIX, PREFIX])
        self.assertEqual([r.position for r in view.rows], [0, 1])
        self.assertEqual([r.app_id for r in view.rows],
                         ["org.mozilla.firefox", "org.example.Firebird"])
        self.assertEqual(view.favorite_count, 0)

    def test_blank_query_uses_catalog_order(self):
        view = proj.project_results("", CATALOG)
        self.assertEqual(view.status, proj.STATUS_READY)
        self.assertEqual(view.key, "")
        self.assertEqual([r.title for r in view.rows],
                         [t for _, t in CATALOG])
        self.assertTrue(all(r.score == ANY for r in view.rows))
        self.assertEqual([r.position for r in view.rows],
                         list(range(len(CATALOG))))

    def test_whitespace_query_treated_as_blank(self):
        view = proj.project_results("   ", CATALOG)
        self.assertEqual(view.key, "")
        self.assertEqual([r.title for r in view.rows],
                         [t for _, t in CATALOG])

    def test_no_match_is_empty(self):
        view = proj.project_results("zzzznotpresent", CATALOG)
        self.assertEqual(view.status, proj.STATUS_EMPTY)
        self.assertEqual(view.rows, ())
        self.assertEqual(view.favorite_count, 0)
        self.assertEqual(view.key, "zzzznotpresent")

    def test_to_dict_is_plain_bounded_mapping(self):
        view = proj.project_results("fire", CATALOG,
                                    favorites=["org.mozilla.firefox"])
        data = view.to_dict()
        self.assertEqual(set(data),
                         {"key", "rows", "favorite_count", "status"})
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(set(data["rows"][0]),
                         {"app_id", "title", "score", "favorite", "position"})
        self.assertIsInstance(data["rows"], list)
        self.assertTrue(all(isinstance(r, dict) for r in data["rows"]))

    def test_records_are_immutable(self):
        view = proj.project_results("fire", CATALOG)
        with self.assertRaises(FrozenInstanceError):
            view.status = "X"
        with self.assertRaises(FrozenInstanceError):
            view.rows[0].position = 9

    def test_inputs_not_mutated(self):
        catalog = list(CATALOG)
        favorites = ["org.gnome.Terminal", "org.mozilla.firefox"]
        proj.project_results("term", catalog, favorites=favorites)
        self.assertEqual(catalog, list(CATALOG))
        self.assertEqual(favorites,
                         ["org.gnome.Terminal", "org.mozilla.firefox"])

    def test_repeatable_and_deterministic(self):
        a = proj.project_results("fire", CATALOG,
                                 favorites=["org.example.Firebird"])
        b = proj.project_results("fire", CATALOG,
                                 favorites=["org.example.Firebird"])
        self.assertEqual(a.to_dict(), b.to_dict())


class FavoritesTests(unittest.TestCase):
    def test_favorite_marker_on_matched_row(self):
        view = proj.project_results("fire", CATALOG,
                                    favorites=["org.example.Firebird"])
        self.assertEqual(view.favorite_count, 1)
        by_id = {r.app_id: r for r in view.rows}
        self.assertTrue(by_id["org.example.Firebird"].favorite)
        self.assertFalse(by_id["org.mozilla.firefox"].favorite)

    def test_favorite_leads_on_equal_score(self):
        # Firefox and Firebird both classify as EXACT for "fire"; making the
        # later catalog entry a favorite must move it ahead deterministically.
        view = proj.project_results("fire", CATALOG,
                                    favorites=["org.example.Firebird"])
        self.assertEqual([r.app_id for r in view.rows],
                         ["org.example.Firebird", "org.mozilla.firefox"])

    def test_favorite_does_not_override_better_score(self):
        # A weaker-scored favorite must stay behind a stronger non-favorite.
        catalog = (
            ("org.example.Fav", "Fav Firework"),   # SUBSTRING
            ("org.example.Exact", "Fire"),          # EXACT
        )
        view = proj.project_results("fire", catalog,
                                    favorites=["org.example.Fav"])
        self.assertEqual(view.rows[0].app_id, "org.example.Exact")
        self.assertFalse(view.rows[0].favorite)
        self.assertEqual(view.rows[1].app_id, "org.example.Fav")
        self.assertTrue(view.rows[1].favorite)
        self.assertEqual(view.favorite_count, 1)

    def test_blank_query_favorites_first_in_display_order(self):
        view = proj.project_results(
            "", CATALOG,
            favorites=["org.example.Firebird", "org.gnome.Terminal"],
        )
        self.assertEqual([r.app_id for r in view.rows], [
            "org.example.Firebird",
            "org.gnome.Terminal",
            "org.mozilla.firefox",
            "org.gnome.Nautilus",
            "org.example.Chronicle",
        ])
        self.assertEqual(view.favorite_count, 2)

    def test_uninstalled_favorite_is_hidden_without_error(self):
        view = proj.project_results(
            "", CATALOG, favorites=["org.example.Gone", "org.gnome.Terminal"])
        self.assertEqual(view.favorite_count, 1)
        self.assertNotIn("org.example.Gone",
                         [r.app_id for r in view.rows])

    def test_duplicate_favorite_counted_once(self):
        view = proj.project_results(
            "fire", CATALOG,
            favorites=["org.mozilla.firefox", "org.mozilla.firefox"])
        self.assertEqual(view.favorite_count, 1)

    def test_favorites_generator_accepted(self):
        view = proj.project_results(
            "fire", CATALOG,
            favorites=(x for x in ["org.example.Firebird"]))
        self.assertEqual(view.favorite_count, 1)


class InputValidationTests(unittest.TestCase):
    def test_query_wrong_type(self):
        for bad in (None, 5, b"fire", [], {}):
            with self.subTest(bad=bad):
                with self.assertRaises(proj.ProjectionError):
                    proj.project_results(bad, CATALOG)

    def test_query_too_long(self):
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("a" * (MAX_QUERY_CHARS + 1), CATALOG)

    def test_limit_wrong_type(self):
        for bad in (True, False, "4", 4.0, None):
            with self.subTest(bad=bad):
                with self.assertRaises(proj.ProjectionError):
                    proj.project_results("fire", CATALOG, limit=bad)

    def test_limit_out_of_range(self):
        for bad in (0, -1, MAX_RESULTS + 1):
            with self.subTest(bad=bad):
                with self.assertRaises(proj.ProjectionError):
                    proj.project_results("fire", CATALOG, limit=bad)

    def test_catalog_top_type_rejected(self):
        for bad in ("Firefox", b"Firefox", None, 5, {1: 2}):
            with self.subTest(bad=bad):
                with self.assertRaises(proj.ProjectionError):
                    proj.project_results("fire", bad)

    def test_catalog_empty_rejected(self):
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("fire", [])

    def test_catalog_malformed_entry_rejected(self):
        for bad in (
            ["org.example.A", "Alpha", "extra"],
            "org.example.A",
            ["org.example.A"],
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(proj.ProjectionError):
                    proj.project_results("fire", [bad])

    def test_catalog_invalid_app_id_rejected(self):
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("fire", [("bad id!", "Alpha")])

    def test_catalog_duplicate_app_id_rejected(self):
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("fire", [
                ("org.example.A", "Alpha"),
                ("org.example.A", "Beta"),
            ])

    def test_catalog_oversized_rejected(self):
        big = [(f"org.example.App{i}", f"App{i}")
               for i in range(MAX_CANDIDATES + 1)]
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("", big)

    def test_title_wrong_type_rejected(self):
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("fire", [("org.example.A", 5)])

    def test_title_too_long_rejected(self):
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("fire", [("org.example.A", "a" * 257)])

    def test_favorites_wrong_type_rejected(self):
        for bad in ("org.example.A", 5, {1, 2}):
            with self.subTest(bad=bad):
                with self.assertRaises(proj.ProjectionError):
                    proj.project_results("fire", CATALOG, favorites=bad)

    def test_favorites_invalid_id_rejected(self):
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("fire", CATALOG,
                                 favorites=["bad id!"])

    def test_favorites_over_bound_rejected(self):
        many = [f"org.example.App{i}" for i in range(17)]
        with self.assertRaises(proj.ProjectionError):
            proj.project_results("fire", CATALOG, favorites=many)


class AgreementGateTests(unittest.TestCase):
    def test_ranking_focus_disagreement_fails_closed(self):
        # If a broken ranking source emits a name that is not the catalog
        # title at its index, the projection must refuse rather than emit a
        # row pointing at the wrong application.
        wrong = (Match(name="NotInCatalog", score=EXACT, index=0),)
        with patch.object(proj, "rank_matches", return_value=wrong):
            with self.assertRaises(proj.ProjectionError):
                proj.project_results("fire", CATALOG)

    def test_favorite_flag_agrees_with_favorites_set(self):
        view = proj.project_results(
            "fire", CATALOG,
            favorites=["org.example.Firebird"])
        favorites = {"org.example.Firebird"}
        for row in view.rows:
            self.assertEqual(row.favorite, row.app_id in favorites)
        self.assertEqual(view.favorite_count,
                         sum(1 for r in view.rows if r.favorite))

    def test_positions_contiguous(self):
        view = proj.project_results("", CATALOG)
        self.assertEqual([r.position for r in view.rows],
                         list(range(len(view.rows))))


if __name__ == "__main__":
    unittest.main()
