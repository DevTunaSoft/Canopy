"""Offline unit tests for bounded Unicode-aware launcher name matching.

No Qt runtime, desktop session, Linux Mint VM or real compiled application is
used. These tests cover pure-Python matching only.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.launcher.app_search_casefold import (
    ANY, EXACT, MAX_CANDIDATES, MAX_NAME_CHARS, MAX_QUERY_CHARS, MAX_RESULTS,
    PREFIX, SUBSTRING, AppSearchError, Match, matches, normalize_for_search,
    normalize_name, rank_matches,
)


class AppSearchCasefoldTests(unittest.TestCase):
    def test_basic_case_insensitive_substring_and_rank_order(self):
        names = ["Notepad", "Files", "Browser", "File Manager"]
        ranked = rank_matches("file", names)
        self.assertEqual([m.name for m in ranked], ["Files", "File Manager"])
        self.assertEqual([m.score for m in ranked], [PREFIX, PREFIX])
        ranked = rank_matches("ILE", names)
        self.assertEqual([(m.name, m.score) for m in ranked],
                         [("Files", SUBSTRING), ("File Manager", SUBSTRING)])
        self.assertFalse(matches("xyz", "Files"))
        self.assertEqual([m.name for m in rank_matches("zzz", names)], [])

    def test_exact_beats_prefix_beats_substring_with_stable_input_order(self):
        names = ["Terminal Emulator", "term", "MyTerminal", "Terminal"]
        ranked = rank_matches("terminal", names)
        self.assertEqual([(m.name, m.score) for m in ranked], [
            ("Terminal", EXACT),
            ("Terminal Emulator", PREFIX),
            ("MyTerminal", SUBSTRING),
        ])
        self.assertEqual([m.index for m in ranked], [3, 0, 2])

    def test_casefold_collision_german_sharp_s(self):
        self.assertEqual(normalize_name("Straße"), "strasse")
        self.assertEqual(normalize_for_search("STRASSE"), "strasse")
        self.assertTrue(matches("STRASSE", "Straße"))
        self.assertTrue(matches("strasse", "Straße"))
        self.assertTrue(matches("straße", "STRASSE"))
        ranked = rank_matches("STRASSE", ["Straße", "Other"])
        self.assertEqual([(m.name, m.score) for m in ranked], [("Straße", EXACT)])

    def test_casefold_collision_greek_final_sigma(self):
        # Final sigma (ς) and normal sigma (σ) share one casefold key.
        self.assertEqual("ΟΔΟΣ".casefold(), "οδος".casefold())
        self.assertTrue(matches("οδος", "ΟΔΟΣ"))
        self.assertTrue(matches("ΟΔΟΣ", "οδος"))
        self.assertTrue(matches("οδο", "ΟΔΟΣ"))  # prefix still matches

    def test_casefold_collision_ligature_and_turkish_dotted_i(self):
        # Latin ligature folds to a plain letter sequence.
        self.assertEqual(normalize_name("ﬀinity"), "ffinity")
        self.assertTrue(matches("affinity", "Aﬀinity"))
        # Turkish dotted capital I folds to i + combining dot, not plain i.
        self.assertEqual(normalize_for_search("İ"), "i\u0307")
        self.assertTrue(matches("İ", "i\u0307"))
        # Negative control: dotless i is a different letter under casefold.
        self.assertFalse(matches("i", "ı"))
        self.assertFalse(matches("ı", "i"))

    def test_nfkc_compatibility_and_whitespace(self):
        self.assertEqual(normalize_for_search("ＡＰＰ"), "app")
        self.assertTrue(matches("app", "ＡＰＰ"))
        self.assertEqual(normalize_for_search("  FILE  "), "file")
        self.assertTrue(matches("  file  ", "  Files  "))
        self.assertEqual(normalize_for_search(" \u00a0 "), "")
        self.assertEqual(len(rank_matches("   ", ["Files", "Browser"])), 2)

    def test_empty_query_returns_every_name_in_input_order(self):
        names = ["Zebra", "Files", "Browser"]
        ranked = rank_matches("", names)
        self.assertEqual([m.name for m in ranked], names)
        self.assertEqual([m.score for m in ranked], [ANY, ANY, ANY])
        self.assertEqual([m.index for m in ranked], [0, 1, 2])

    def test_very_long_query_is_rejected_and_boundary_is_accepted(self):
        with self.assertRaisesRegex(AppSearchError, "query exceeds"):
            normalize_for_search("a" * (MAX_QUERY_CHARS + 1))
        with self.assertRaisesRegex(AppSearchError, "query exceeds"):
            rank_matches("a" * 100_000, ["Files"])
        boundary = "a" * MAX_QUERY_CHARS
        self.assertEqual(len(normalize_for_search(boundary)), MAX_QUERY_CHARS)
        self.assertTrue(matches(boundary, boundary))
        # Rejection happens before candidate scoring: no oversized work.
        with self.assertRaisesRegex(AppSearchError, "query exceeds"):
            matches("a" * (MAX_QUERY_CHARS + 1), "b" * 5000)

    def test_very_long_name_and_casefold_expansion_are_bounded(self):
        with self.assertRaisesRegex(AppSearchError, "name exceeds"):
            normalize_name("a" * (MAX_NAME_CHARS + 1))
        with self.assertRaisesRegex(AppSearchError, "name exceeds"):
            matches("a", "b" * 100_000)
        # Sharp-s casefold doubles the length; still inside the normalized cap.
        expanded = "ß" * MAX_NAME_CHARS
        self.assertEqual(len(normalize_name(expanded)), 2 * MAX_NAME_CHARS)
        # A single compatibility code point can expand far past its own length.
        long_form = "\ufdfa" * 200
        self.assertLess(len(long_form), 1024)
        with self.assertRaisesRegex(AppSearchError, "normalized name exceeds bound"):
            normalize_name(long_form)

    def test_candidate_count_and_result_limit_are_bounded(self):
        names = ["App" + str(i) for i in range(MAX_CANDIDATES + 1)]
        with self.assertRaisesRegex(AppSearchError, "candidate count exceeds"):
            rank_matches("app", names)
        self.assertEqual(len(names), MAX_CANDIDATES + 1)
        big = ["App" + str(i) for i in range(MAX_CANDIDATES)]
        self.assertEqual(len(rank_matches("", big)), MAX_RESULTS)
        for bad in (0, -1, MAX_RESULTS + 1, True, 2.0, "2", None):
            with self.subTest(limit=repr(bad)):
                with self.assertRaises(AppSearchError):
                    rank_matches("app", ["App"], limit=bad)

    def test_input_validation_is_fail_closed(self):
        for bad in (None, 42, b"Files", ["Files"], ("Files",)):
            with self.subTest(query=repr(bad)):
                with self.assertRaisesRegex(AppSearchError, "query must be a string"):
                    normalize_for_search(bad)
        for bad in (None, 42, b"Files"):
            with self.subTest(name=repr(bad)):
                with self.assertRaisesRegex(AppSearchError, "name must be a string"):
                    normalize_name(bad)
        with self.assertRaisesRegex(AppSearchError, "not valid Unicode"):
            normalize_for_search("\ud800")
        with self.assertRaisesRegex(AppSearchError, "candidates must be a list or tuple"):
            rank_matches("app", (name for name in ["App"]))

    def test_results_are_immutable_and_inputs_are_not_mutated(self):
        names = ["Files", "Browser"]
        snapshot = list(names)
        result = rank_matches("", names)
        self.assertIsInstance(result, tuple)
        self.assertIsInstance(result[0], Match)
        self.assertEqual(names, snapshot)
        with self.assertRaises(FrozenInstanceError):
            result[0].score = 99

    def test_no_polling_services_Qt_or_platform_specific_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/launcher/app_search_casefold.py").read_text(encoding="utf-8")
        for forbidden in ("QTimer", "QtCore", "PyQt", "PySide", "subprocess",
                          "import socket", "Thread(", "asyncio", "time.sleep", "while ",
                          "import os", "sys.platform", "winreg", "requests", "open("):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
