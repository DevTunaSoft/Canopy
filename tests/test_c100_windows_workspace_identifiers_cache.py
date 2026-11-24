"""RED/GREEN resource regression: lazy cached WorkspaceInventory identifiers."""
from dataclasses import FrozenInstanceError
import unittest

from canopy_features.windows import workspace_inventory as w


class IdentifiersCacheTests(unittest.TestCase):
    def _inv(self):
        return w.build_inventory(
            [{"source": "test", "name": "Alpha", "identifier": "alpha"},
             {"source": "test", "name": "Beta", "identifier": "beta"}],
            permitted_sources=frozenset({"test"}))

    def test_repeated_reads_return_same_object(self):
        inv = self._inv()
        first = inv.identifiers()
        self.assertIsInstance(first, tuple)
        self.assertTrue(first)
        self.assertIs(first, inv.identifiers())

    def test_content_unchanged(self):
        inv = self._inv()
        self.assertEqual(inv.identifiers(), ("alpha", "beta"))

    def test_distinct_instances_do_not_share_cache(self):
        a, b = self._inv(), self._inv()
        self.assertIsNot(a.identifiers(), b.identifiers())
        self.assertEqual(a.identifiers(), b.identifiers())

    def test_inventory_stays_frozen(self):
        inv = self._inv()
        inv.identifiers()
        with self.assertRaises(FrozenInstanceError):
            inv.workspaces = ()
        self.assertEqual(inv.identifiers(), ("alpha", "beta"))

    def test_both_caches_coexist_after_rebase(self):
        inv = self._inv()
        ids = inv.identifiers()
        found = inv.get("beta")
        self.assertEqual(ids, ("alpha", "beta"))
        self.assertEqual(found.identifier, "beta")
        self.assertIs(ids, inv.identifiers())
        self.assertIs(found, inv.get("beta"))
        self.assertIsNone(inv.get("missing"))

    def test_empty_inventory_returns_empty_tuple(self):
        inv = w.WorkspaceInventory((), ())
        self.assertEqual(inv.identifiers(), ())
        self.assertIs(inv.identifiers(), inv.identifiers())


if __name__ == "__main__":
    unittest.main()
