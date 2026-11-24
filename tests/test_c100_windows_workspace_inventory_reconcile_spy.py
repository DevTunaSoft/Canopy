"""Deterministic RED/GREEN regression for reconcile() lookup complexity.

A SpyStr identifier counts equality comparisons. The old implementation used
shared_previous.index(identifier) inside a loop, giving O(n^2) comparisons.
The fixed implementation builds one id->index map, giving O(n).
"""
import unittest

from canopy_features.windows import workspace_inventory as w

COUNTER = {"eq": 0}


class SpyStr(str):
    def __eq__(self, other):
        COUNTER["eq"] += 1
        return str.__eq__(self, other)

    def __hash__(self):
        return str.__hash__(self)


def _inv(identifiers, names=None, *, spy=False):
    records = []
    for index, identifier in enumerate(identifiers):
        name = (names or {}).get(identifier, "name-" + str(identifier))
        records.append(w.Workspace(
            SpyStr(identifier) if spy else identifier, name, "test"))
    return w.WorkspaceInventory(tuple(records), ())


class ReconcileLookupTests(unittest.TestCase):
    def test_linear_lookup_bound(self):
        n = 64
        previous = _inv(["w%d" % i for i in range(n)], spy=True)
        current = _inv(["w%d" % i for i in reversed(range(n))], spy=True)
        COUNTER["eq"] = 0
        result = w.reconcile(previous, current)
        scans = COUNTER["eq"]
        self.assertEqual(len(result.reordered), n)
        self.assertLessEqual(scans, 8 * n,
                             "reconcile performed %d equality scans for n=%d"
                             % (scans, n))

    def test_exact_order_and_diffs_preserved(self):
        previous = _inv(["a", "b", "c", "d"],
                        names={"a": "A", "b": "B", "c": "C", "d": "D"})
        current = _inv(["d", "c", "b", "e"],
                       names={"d": "D", "c": "C-renamed", "b": "B", "e": "E"})
        result = w.reconcile(previous, current)
        self.assertEqual(result.added, ("e",))
        self.assertEqual(result.removed, ("a",))
        self.assertEqual(result.renamed, ("c",))
        self.assertEqual(result.reordered, ("d", "b"))
        self.assertIs(result.inventory, current)

    def test_no_diffs_for_identical_inventories(self):
        inv = _inv(["a", "b"])
        result = w.reconcile(inv, inv)
        self.assertEqual(result.added, ())
        self.assertEqual(result.removed, ())
        self.assertEqual(result.renamed, ())
        self.assertEqual(result.reordered, ())

    def test_duplicate_identifiers_keep_first_occurrence(self):
        previous = w.WorkspaceInventory(
            (w.Workspace("a", "A", "test"), w.Workspace("a", "A2", "test")),
            ())
        current = w.WorkspaceInventory((w.Workspace("a", "A2", "test"),), ())
        result = w.reconcile(previous, current)
        self.assertEqual(result.renamed, ())
        self.assertEqual(result.reordered, ())

    def test_fail_closed_wrong_types(self):
        for args in ((None, _inv(["a"])), (_inv(["a"]), None)):
            with self.assertRaises(w.WorkspaceInventoryError):
                w.reconcile(*args)


if __name__ == "__main__":
    unittest.main()
