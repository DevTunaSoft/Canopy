import unittest
from scripts.pr_stack_audit import audit


def pr(number, head, base, draft=True):
    return {"number": number, "head": {"ref": head},
            "base": {"ref": base}, "draft": draft}


class PrStackAuditTests(unittest.TestCase):
    def test_stacked_prs_are_ordered_and_not_merged(self):
        result = audit([pr(3, "classic", "preferences"),
                        pr(1, "foundation", "main"),
                        pr(2, "preferences", "foundation")])
        self.assertEqual([x["number"] for x in result["prs"]], [1, 2, 3])
        self.assertEqual(result["prs"][-1]["dependencies_nearest_first"], [2, 1])
        self.assertEqual(result["roots"], [1])
        self.assertFalse(result["merge_performed"])

    def test_independent_main_roots_require_review(self):
        result = audit([pr(1, "docs", "main"), pr(24, "visual", "main")])
        self.assertEqual(len(result["roots"]), 2)
        self.assertTrue(result["warnings"])

    def test_unknown_base_is_blocked(self):
        result = audit([pr(2, "prefs", "absent")])
        self.assertEqual(result["prs"][0]["integration_status"], "BLOCKED_UNKNOWN_BASE")

    def test_cycle_and_duplicate_heads_rejected(self):
        cases = ([pr(1, "a", "b"), pr(2, "b", "a")],
                 [pr(1, "a", "main"), pr(2, "a", "main")],
                 [pr(1, "a", "a")])
        for items in cases:
            with self.subTest(items=items), self.assertRaises(ValueError):
                audit(items)

    def test_malformed_prs_rejected(self):
        cases = ([pr(1, "a", "main"), pr(1, "b", "main")],
                 [{"number": 2, "head": None, "base": {}}],
                 [pr(True, "a", "main")])
        for items in cases:
            with self.subTest(items=items), self.assertRaises(ValueError):
                audit(items)

    def test_open_non_draft_is_flagged(self):
        result = audit([pr(1, "a", "main", draft=False)])
        self.assertIn("not draft", " ".join(result["warnings"]))


if __name__ == "__main__":
    unittest.main()
