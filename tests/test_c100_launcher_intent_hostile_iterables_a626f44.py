"""Fail-closed contract for hostile-but-bounded catalog and favorites inputs.

A launcher decision must never leak a raw exception from a caller-supplied
catalog or favorites source: an input that cannot be fully read is invalid,
and the composer's own domain error is the only boundary it may expose. This
closes the same gap for the remaining caller-supplied iterables that the
allowlist path already closes (PR #432). Pure/offline; no Qt, GIO, process
launch or desktop is involved.
"""
import unittest

from canopy_features.launcher.launcher_intent_summary import (
    STATUS_READY,
    LauncherIntentError,
    summarize_launcher_intent,
)

CATALOG = (
    ("safe.desktop", "Firefox"),
    ("other.desktop", "Files"),
)


class FailingSource:
    """A bounded source that yields legal items, then fails while being read."""

    def __init__(self, items=(), exc=None):
        self.items = tuple(items)
        self.exc = exc if exc is not None else OSError("catalog source unavailable")
        self.consumed = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.consumed < len(self.items):
            item = self.items[self.consumed]
            self.consumed += 1
            return item
        self.consumed += 1
        raise self.exc


class HostileCatalogAndFavoritesTests(unittest.TestCase):
    """Read failures on caller inputs must surface as LauncherIntentError."""

    def test_catalog_read_failure_is_domain_error_not_raw_exception(self):
        source = FailingSource(CATALOG, RuntimeError("boom"))
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("fire", source,
                                      allowed_app_ids={"safe.desktop"})
        self.assertLessEqual(source.consumed, len(CATALOG) + 1)

    def test_catalog_os_error_is_domain_error_not_raw_exception(self):
        source = FailingSource(CATALOG, OSError("source unavailable"))
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("", source)

    def test_favorites_read_failure_is_domain_error_not_raw_exception(self):
        source = FailingSource(("other.desktop",), RuntimeError("boom"))
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("", CATALOG, favorites=source,
                                      allowed_app_ids={"safe.desktop"})
        self.assertLessEqual(source.consumed, 2)

    def test_favorites_read_failure_on_query_path_is_domain_error(self):
        source = FailingSource(("other.desktop",), OSError("source unavailable"))
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("fire", CATALOG, favorites=source)


class WellFormedGeneratorTests(unittest.TestCase):
    """Ordinary lazy iterables must keep working after the fail-closed guard."""

    def test_catalog_generator_still_yields_ready(self):
        result = summarize_launcher_intent(
            "fire", (entry for entry in CATALOG),
            allowed_app_ids={"safe.desktop"})
        self.assertEqual(result.status, STATUS_READY)
        self.assertEqual(result.selected_app_id, "safe.desktop")

    def test_favorites_generator_still_kept_in_order(self):
        result = summarize_launcher_intent(
            "", CATALOG, favorites=(x for x in ("other.desktop", "safe.desktop")))
        self.assertEqual(result.favorites, ("other.desktop", "safe.desktop"))


if __name__ == "__main__":
    unittest.main()
