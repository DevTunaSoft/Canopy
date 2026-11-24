"""Regression tests for bounded row materialization in favorites projection.

Run: python -m unittest tests.test_c100_launcher_favorites_projection_lazy_rows -v
"""
import unittest
from unittest.mock import patch

from canopy_features.launcher import launcher_favorites_projection as projection
from canopy_features.launcher.launcher_favorites_projection import (
    ANY,
    STATUS_READY,
    ProjectionError,
    project_results,
)

CATALOG = tuple(
    ("app%04d.desktop" % i, "App %04d" % i) for i in range(1, 41)
)
FAVORITES = ("app0003.desktop", "app0001.desktop")


class BoundedMaterializationTests(unittest.TestCase):
    def test_build_rows_receives_the_result_limit(self):
        with patch.object(projection, "_build_rows",
                          wraps=projection._build_rows) as spy:
            project_results("", CATALOG, favorites=FAVORITES, limit=7)
        self.assertEqual(spy.call_args.kwargs.get("limit"), 7)

    def test_blank_query_rows_are_limited_and_favorites_lead(self):
        result = project_results("", CATALOG, favorites=FAVORITES, limit=3)
        self.assertEqual(result.status, STATUS_READY)
        self.assertEqual([row.app_id for row in result.rows], [
            "app0003.desktop", "app0001.desktop", "app0002.desktop"])
        self.assertEqual([row.score for row in result.rows], [ANY] * 3)
        self.assertEqual([row.position for row in result.rows], [0, 1, 2])

    def test_blank_query_limit_one_keeps_first_favorite(self):
        result = project_results("", CATALOG, favorites=FAVORITES, limit=1)
        self.assertEqual([row.app_id for row in result.rows], ["app0003.desktop"])
        self.assertEqual(result.favorite_count, 1)

    def test_large_catalog_blank_query_respects_limit(self):
        large = tuple(("big%04d.desktop" % i, "Big %04d" % i)
                      for i in range(4096))
        result = project_results("", large, limit=64)
        self.assertEqual(len(result.rows), 64)
        self.assertEqual(result.rows[-1].position, 63)

    def test_nonblank_query_result_is_unchanged(self):
        result = project_results("App 0005", CATALOG, favorites=FAVORITES)
        self.assertEqual(result.rows[0].app_id, "app0005.desktop")
        self.assertEqual(result.rows[0].score, 3)
        self.assertEqual(result.favorite_count, 0)

    def test_to_dict_shape(self):
        payload = project_results("", CATALOG, limit=2).to_dict()
        self.assertEqual(set(payload), {
            "key", "rows", "favorite_count", "status"})


class FailClosedTests(unittest.TestCase):
    def test_invalid_limits_still_rejected(self):
        for limit in (True, 0, -1, 65, "7"):
            with self.subTest(limit=limit):
                with self.assertRaises(ProjectionError):
                    project_results("", CATALOG, limit=limit)

    def test_malformed_catalog_still_rejected(self):
        with self.assertRaises(ProjectionError):
            project_results("", CATALOG + (("broken",),))

    def test_unknown_favorites_hidden(self):
        result = project_results(
            "", CATALOG, favorites=("gone.desktop", "app0001.desktop"))
        self.assertEqual(result.rows[0].app_id, "app0001.desktop")
        self.assertEqual(result.favorite_count, 1)


if __name__ == "__main__":
    unittest.main()
