"""Residual audit: category display labels must not be hostile-but-valid.

``Category`` is the module's validity gate for a freedesktop menu category:
once constructed, the catalog treats it as a known, valid category.  A bounded
display label carrying a control, format, surrogate, private-use,
noncharacter or line/paragraph separator scalar is still visually hostile but
currently passes that gate.  This test pins the fail-closed behavior without
touching Qt, files, processes or the approved visual appearance.
"""
import unittest

from canopy_features.launcher.app_categories import (
    Category,
    CategoryCatalog,
    CategoryError,
)

# Every probe is short and finite; only the scalar class is hostile.
_UNSAFE_LABELS = (
    "Ga\x85me",      # Cc: C1 NEL
    "Ga\x1cme",      # Cc: C0 separator eaten by str.strip()
    "Ga\u200bme",    # Cf: zero-width space
    "Ga\u202eme",    # Cf: right-to-left override
    "Ga\ue000me",    # Co: private use
    "Ga\u2028me",    # Zl: line separator
    "Ga\u2029me",    # Zp: paragraph separator
    "Ga\u0378me",    # Cn: unassigned
    "Ga\ud800me",    # Cs: lone surrogate (raises on UTF-8 encoding)
)


class HostileCategoryDisplayLabelTests(unittest.TestCase):
    def test_unsafe_display_label_is_refused_by_category_gate(self):
        for label in _UNSAFE_LABELS:
            with self.subTest(label=ascii(label)):
                with self.assertRaises(CategoryError):
                    Category("X-Label", label, 5)

    def test_unsafe_display_label_cannot_make_catalog_entry_valid(self):
        with self.assertRaises(CategoryError):
            CategoryCatalog(extra=[Category("X-Label", "Ga\u202eme", 5)])

    def test_legitimate_unicode_display_label_still_resolves(self):
        label = "Caf\u00e9 / \u65e5\u672c\u8a9e"
        category = Category("X-Label", label, 5)
        catalog = CategoryCatalog(extra=[category])
        shown = [c.display_name for c in catalog.categories if c.id == "X-Label"]
        self.assertEqual(shown, [label])
        self.assertEqual(catalog.resolve(["X-Label"]).known, (category,))


if __name__ == "__main__":
    unittest.main()
