"""Regression tests: the application catalog passed to order_applications is bounded.

app_categories documents that bounds keep work and memory bounded regardless of
input size.  Category ids, tokens and catalog categories are capped, but the
``applications`` iterable was consumed without any cap.  These tests prove the
missing invariant with finite oversized inputs (never an infinite iterable).
"""
import unittest

from canopy_features.launcher import app_categories as ac

# The cap is asserted against the module attribute (which is absent on the
# unfixed code) and against an explicit value so the over-bound inputs are
# finite and deterministic.
LIMIT = 4096


def _app(index):
    return ac.Application(
        id="org.example.app%d" % index,
        title="App %d" % index,
        categories=("Utility",),
    )


class ApplicationCatalogBoundTests(unittest.TestCase):
    def setUp(self):
        self.catalog = ac.CategoryCatalog()

    def test_module_exposes_application_bound(self):
        self.assertEqual(ac.MAX_APPLICATIONS, LIMIT)

    def test_accepts_exactly_the_bound(self):
        ordered = ac.order_applications([_app(i) for i in range(LIMIT)], self.catalog)
        self.assertEqual(len(ordered), LIMIT)

    def test_rejects_one_more_than_the_bound(self):
        with self.assertRaises(ac.CategoryError):
            ac.order_applications([_app(i) for i in range(LIMIT + 1)], self.catalog)

    def test_rejects_oversized_stream_without_full_materialization(self):
        def stream():
            for index in range(LIMIT + 1):
                yield _app(index)

        with self.assertRaises(ac.CategoryError):
            ac.order_applications(stream(), self.catalog)

    def test_control_empty_catalog(self):
        self.assertEqual(ac.order_applications([], self.catalog), ())

    def test_control_wrong_catalog_type(self):
        with self.assertRaises(ac.CategoryError):
            ac.order_applications([_app(0)], object())

    def test_control_non_application_entry(self):
        with self.assertRaises(ac.CategoryError):
            ac.order_applications([object()], self.catalog)

    def test_control_small_catalog_order_is_unchanged(self):
        apps = [
            ac.Application("org.example.z", "Zebra", ("Utility",)),
            ac.Application("org.example.a", "Alpha", ("Development",)),
        ]
        ordered = ac.order_applications(apps, self.catalog)
        self.assertEqual([app.id for app in ordered],
                         ["org.example.a", "org.example.z"])


if __name__ == "__main__":
    unittest.main()
