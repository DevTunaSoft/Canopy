"""Hostile-but-bounded wrong-type Desktop Entry text must fail closed.

Pure in-memory contract test: no Qt, GIO, desktop session, filesystem walk or
process launch is involved. A str subclass passes ``isinstance(text, str)``
but can override ``splitlines()``. With that hole the action parser either
emits a false action-safe claim (duplicate declarations hidden from the scan)
or leaks a raw AttributeError from a wrong-type line. The documented domain
error for unacceptable text is TypeError, so callers can fail closed.

Run: python -m unittest tests.test_c100_apps_desktop_actions_hostile_text_type_5480ad6 -v
"""

import unittest

from canopy_features.apps.desktop_actions import parse_desktop_actions


class DuplicatesHidden(str):
    """Bounded hostile text: hides the real lines from the parser."""

    def splitlines(self, keepends=False):
        return []


class WrongTypeLines(str):
    """Bounded hostile text: yields one wrong-type line."""

    def splitlines(self, keepends=False):
        return ["[Desktop Entry]", 7]


class HostileDesktopEntryTextTests(unittest.TestCase):
    def test_hidden_duplicate_declarations_cannot_claim_safe(self):
        # The supplied text declares "open" twice. A subclass that lies about
        # splitlines() currently yields ok=True (a false action-safe claim);
        # the exact-type gate must reject it with TypeError instead.
        text = DuplicatesHidden(
            "[Desktop Entry]\nActions=open;open;\n"
            "[Desktop Action open]\nExec=demo --open\n")
        with self.assertRaises(TypeError):
            parse_desktop_actions(text)

    def test_wrong_type_line_cannot_leak_raw_exception(self):
        # A wrong-type line currently escapes as AttributeError from
        # raw_line.strip(), not as the parser's TypeError.
        text = WrongTypeLines("[Desktop Entry]\n")
        with self.assertRaises(TypeError):
            parse_desktop_actions(text)

    def test_non_string_text_still_raises_type_error(self):
        for value in (None, 7, b"[Desktop Entry]", ["[Desktop Entry]"]):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    parse_desktop_actions(value)  # type: ignore[arg-type]

    def test_plain_text_contract_is_unchanged(self):
        good = ("[Desktop Entry]\nActions=open;\n"
                "[Desktop Action open]\nExec=demo --open\n")
        scan = parse_desktop_actions(good)
        self.assertTrue(scan.ok, scan.problems)
        self.assertEqual(scan.declared_ids, ("open",))

        duplicate = good.replace("Actions=open;", "Actions=open;open;")
        scan = parse_desktop_actions(duplicate)
        self.assertFalse(scan.ok)
        self.assertIn("duplicate-action",
                      [problem.code for problem in scan.problems])


if __name__ == "__main__":
    unittest.main()
