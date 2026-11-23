"""Regression tests: malformed installed-app catalogs must not destroy favorites.

Offline unit tests only. No Qt runtime, desktop session, network, process
launch or Mint VM is involved. These tests do not prove a working desktop.
"""
import tempfile
import unittest
from pathlib import Path

from canopy_features.launcher import launcher_favorites as favorites


class InstalledCatalogTypeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "favorites.json"
        self.store = favorites.FavoritesStore(self.path)
        for app_id in ("org.example.One", "org.example.Two"):
            self.assertTrue(self.store.add(app_id))
        self._persisted = self.path.read_bytes()

    def tearDown(self):
        self._tmp.cleanup()

    def _assert_intact(self):
        self.assertEqual(self.store.ids(),
                         ("org.example.One", "org.example.Two"))
        self.assertEqual(self.path.read_bytes(), self._persisted)

    def test_visible_refuses_bare_string(self):
        # A bare id is ONE id, not an iterable of single-character ids.
        # Coercing it to a set hides every real favorite.
        with self.assertRaises(favorites.FavoritesError):
            self.store.visible("org.example.One")
        self._assert_intact()

    def test_visible_refuses_bytes_and_bytearray(self):
        for value in (b"org.example.One", bytearray(b"org.example.One")):
            with self.subTest(value=repr(value)):
                with self.assertRaises(favorites.FavoritesError):
                    self.store.visible(value)
                self._assert_intact()

    def test_visible_refuses_mapping(self):
        with self.assertRaises(favorites.FavoritesError):
            self.store.visible({"org.example.One": 1})
        self._assert_intact()

    def test_visible_refuses_none_and_non_iterables(self):
        for value in (None, 7, True):
            with self.subTest(value=repr(value)):
                with self.assertRaises(favorites.FavoritesError):
                    self.store.visible(value)
                self._assert_intact()

    def test_visible_refuses_unhashable_entries(self):
        with self.assertRaises(favorites.FavoritesError):
            self.store.visible([["org.example.One"]])
        self._assert_intact()

    def test_prune_refuses_bare_string_without_erasing(self):
        # The destructive case: a wrong-type catalog used to persist an
        # empty favorites list and permanently delete the user's choices.
        with self.assertRaises(favorites.FavoritesError):
            self.store.prune("org.example.One")
        self._assert_intact()
        self.assertEqual(favorites.FavoritesStore(self.path).ids(),
                         ("org.example.One", "org.example.Two"))

    def test_prune_refuses_bytes_without_erasing(self):
        for value in (b"org.example.One", bytearray(b"org.example.One")):
            with self.subTest(value=repr(value)):
                with self.assertRaises(favorites.FavoritesError):
                    self.store.prune(value)
                self._assert_intact()

    def test_prune_refuses_mapping_without_erasing(self):
        with self.assertRaises(favorites.FavoritesError):
            self.store.prune({"org.example.One": 1})
        self._assert_intact()

    def test_prune_refuses_unhashable_without_erasing(self):
        with self.assertRaises(favorites.FavoritesError):
            self.store.prune([["org.example.One"]])
        self._assert_intact()

    def test_all_refusals_leave_state_untouched(self):
        refused = ("org.example.One", b"org.example.One",
                   bytearray(b"org.example.One"), None,
                   {"org.example.One": 1}, [["org.example.One"]])
        for value in refused:
            with self.subTest(visible=repr(value)):
                with self.assertRaises(favorites.FavoritesError):
                    self.store.visible(value)
                self._assert_intact()
            with self.subTest(prune=repr(value)):
                with self.assertRaises(favorites.FavoritesError):
                    self.store.prune(value)
                self._assert_intact()

    def test_valid_collection_types_still_work(self):
        for container in (("org.example.One",), ["org.example.One"],
                          {"org.example.One"}, frozenset({"org.example.One"}),
                          iter(["org.example.One"])):
            with self.subTest(container=type(container).__name__):
                self.assertEqual(self.store.visible(container),
                                 ("org.example.One",))
                self._assert_intact()

    def test_empty_collection_is_valid_and_non_destructive(self):
        for container in ((), [], set()):
            with self.subTest(container=type(container).__name__):
                self.assertEqual(self.store.visible(container), ())
                self._assert_intact()


if __name__ == "__main__":
    unittest.main()
