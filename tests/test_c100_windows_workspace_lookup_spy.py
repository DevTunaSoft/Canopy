"""RED/GREEN Spy probe: WorkspaceInventory.get() must be O(1) lookups."""
import unittest

from canopy_features.windows import workspace_inventory as w

COUNTER = {"eq": 0}


class SpyStr(str):
    def __eq__(self, other):
        COUNTER["eq"] += 1
        return str.__eq__(self, other)

    def __hash__(self):
        return str.__hash__(self)


def _inv(n=64, spy=True):
    return w.WorkspaceInventory(
        tuple(w.Workspace(SpyStr("w%d" % i) if spy else "w%d" % i,
                          "name-%d" % i, "test") for i in range(n)), ())


class LookupSpyTests(unittest.TestCase):
    def test_get_uses_constant_lookups(self):
        inv = _inv()
        COUNTER["eq"] = 0
        found = inv.get("w63")
        scans = COUNTER["eq"]
        self.assertIsNotNone(found)
        self.assertEqual(found.identifier, "w63")
        self.assertLessEqual(scans, 16,
                             "get() performed %d identifier comparisons" % scans)

    def test_get_returns_correct_workspace(self):
        inv = _inv(spy=False)
        self.assertEqual(inv.get("w7").name, "name-7")
        self.assertIsNone(inv.get("missing"))

    def test_get_is_case_sensitive(self):
        inv = _inv(spy=False)
        self.assertIsNone(inv.get("W7"))

    def test_empty_inventory_returns_none(self):
        self.assertIsNone(w.WorkspaceInventory((), ()).get("anything"))

    def test_repeated_get_is_consistent(self):
        inv = _inv(spy=False)
        first = inv.get("w10")
        self.assertIs(first, inv.get("w10"))
        self.assertEqual(first.identifier, "w10")


if __name__ == "__main__":
    unittest.main()
