"""Regression: Desktop Entry values must refuse non-printable control/format text.

PR #446 hardened ``TryExec`` in ``desktop_entry_tryexec`` but the parser itself
still stored Cc/Cf (and other unsafe-category) characters verbatim in Name,
Icon, localized Name[xx], etc. A launcher that trusts those fields can render
bidi overrides or zero-width text, so the parser must fail closed.

All cases are offline, bounded and need no Qt, GIO or Linux session.
"""
import sys
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.launcher.desktop_entry_parser import (  # noqa: E402
    MalformedEntryError,
    parse,
)

BASE_LINES = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Version=1.0\n"
    "Name=Canopy Files\n"
    "Exec=/usr/bin/canopy-files --open %f\n"
)

# Three non-printable values from three distinct unsafe Unicode categories.
PROBES = (
    ("Cc BEL in Comment", "Comment=Cafc\u0007 Canopy", "Cc"),
    ("Cf ZWSP in Icon", "Icon=canopy\u200bfiles", "Cf"),
    ("Cf RLO in localized Name[fr]", "Name[fr]=Fichiers\u202e Canopy", "Cf"),
)


def make_data(extra_line: str) -> bytes:
    return (BASE_LINES + extra_line + "\n").encode("utf-8")


class NonPrintableDesktopEntryValueTests(unittest.TestCase):
    def test_three_nonprintable_values_are_rejected(self):
        for label, line, category in PROBES:
            with self.subTest(label=label):
                self.assertEqual(unicodedata.category(
                    next(ch for ch in line if not ch.isprintable())), category)
                with self.assertRaisesRegex(MalformedEntryError, "non-printable"):
                    parse(make_data(line))

    def test_c0_separator_that_strip_folds_is_rejected(self):
        # 0x1f is whitespace to str.strip() but not a str.splitlines() boundary,
        # so on unfixed code it is silently folded into a clean-looking value.
        with self.assertRaisesRegex(MalformedEntryError, "non-printable"):
            parse(make_data("Comment=\x1fApp\x1f"))

    def test_printable_values_still_parse(self):
        # Control: the guard must not reject ordinary printable text, including
        # a no-break space (Zs), which stays allowed.
        entry = parse(make_data("Comment=Caf\u00a0 Canopy \u2014 ready"))
        self.assertEqual(entry.values["Comment"], "Caf\u00a0 Canopy \u2014 ready")


if __name__ == "__main__":
    unittest.main()
