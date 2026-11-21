"""Guard the 99-angle review matrix against missing/duplicated gates.

This is a document-schema test, NOT evidence that unimplemented or blocked
runtime capabilities have passed.
"""
from collections import Counter
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "RELIABILITY_99_GATE_AUDIT.md"
ROW = re.compile(
    r"^\| (R\d{3}) \| (P[012]) \| (CI-SCOPED|GAP|BLOCKED) \| (.+) \|$",
    re.MULTILINE,
)


class ReliabilityMatrixTests(unittest.TestCase):
    def setUp(self):
        self.report = REPORT.read_text(encoding="utf-8")
        self.rows = ROW.findall(self.report)

    def test_ninety_nine_uniquely_numbered_gates(self):
        self.assertEqual(len(self.rows), 99)
        self.assertEqual(
            [row[0] for row in self.rows],
            [f"R{idx:03}" for idx in range(1, 100)],
        )
        self.assertEqual(len(set(row[0] for row in self.rows)), 99)

    def test_eleven_distinct_domains_nine_gates_each(self):
        headings = re.findall(r"^## (?!Classification|Initial totals)(.+)$",
                              self.report, re.MULTILINE)
        self.assertEqual(len(headings), 11)
        self.assertEqual(len(set(headings)), 11)
        parts = re.split(r"^## (?!Classification|Initial totals).+$",
                         self.report, flags=re.MULTILINE)[1:]
        self.assertEqual(len(parts), 11)
        for section in parts:
            self.assertEqual(len(ROW.findall(section)), 9)

    def test_every_entry_has_priority_and_explicit_not_done_status(self):
        priorities = Counter(row[1] for row in self.rows)
        statuses = Counter(row[2] for row in self.rows)
        self.assertGreater(priorities["P0"], 0)
        self.assertGreater(priorities["P1"], 0)
        self.assertGreater(priorities["P2"], 0)
        self.assertGreater(statuses["GAP"], 0)
        self.assertGreater(statuses["BLOCKED"], 0)
        self.assertGreater(statuses["CI-SCOPED"], 0)
        self.assertTrue(all(row[3].strip() for row in self.rows))

    def test_every_p0_gap_remains_explicit(self):
        self.assertIn("A P0 entry cannot be marked complete", self.report)
        self.assertIn("not 99 completed tests", self.report)
        self.assertIn("Do **not** compute a product-wide percent-complete", self.report)
        self.assertIn("No claim of zero bugs", self.report)

    def test_optical_and_mint_acceptance_remain_blocked(self):
        for term in ("optically balanced", "Mint 22.3 Cinnamon",
                     "reboot", "guest VM"):
            self.assertIn(term, self.report)
        self.assertIn("BLOCKED", self.report)
        self.assertIn("skipped CI checks", self.report)
        self.assertIn("incomplete Shell Host cleanup", self.report)

    def test_owner_rules_no_deadline_or_reviewer_recruitment(self):
        self.assertNotIn("November 30", self.report)
        self.assertIn("Do not solicit external reviewers unless requested",
                      self.report)


if __name__ == "__main__":
    unittest.main()
