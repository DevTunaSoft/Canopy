"""Regression: Unicode line-boundary scalars in an entry line must fail closed.

At tip 2051dfd ``parse()`` splits the decoded entry with ``str.splitlines()``
and only afterwards applies its per-line ``_has_nonprintable`` guard.
``splitlines()`` consumes C0 separators (VT/FF/FS/GS/RS), NEL and Zl/Zp before
that guard can observe them, so a hostile line containing one of those scalars
is silently rewritten into two clean-looking lines and ``parse()`` returns a
valid ``DesktopEntry``.  All probes below are offline and bounded.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.launcher.desktop_entry_parser import (  # noqa: E402
    MalformedEntryError,
    parse,
)

# Every scalar here is BOTH a str.splitlines() boundary AND a member of the
# parser's declared unsafe Unicode categories, so the guard at 2051dfd never
# sees it and the smuggled Exec key is accepted as a normal line.
HOSTILE_SEPARATORS = (
    ("VT U+000B", "\x0b"),
    ("FF U+000C", "\x0c"),
    ("FS U+001C", "\x1c"),
    ("GS U+001D", "\x1d"),
    ("RS U+001E", "\x1e"),
    ("NEL U+0085", "\x85"),
    ("LS U+2028", "\u2028"),
    ("PS U+2029", "\u2029"),
)


class HostileLineSeparatorTests(unittest.TestCase):
    def test_line_boundary_scalar_cannot_smuggle_a_key(self):
        for label, separator in HOSTILE_SEPARATORS:
            with self.subTest(label=label):
                # Without the separator this is a two-field line; splitlines()
                # turns it into two legal fields, which must not happen.
                data = (
                    "[Desktop Entry]\nType=Application\nName=App"
                    + separator
                    + "Exec=/bin/true\n"
                ).encode("utf-8")
                with self.assertRaisesRegex(MalformedEntryError, "non-printable"):
                    parse(data)

    def test_bare_cr_inside_a_line_is_rejected(self):
        # CR is another splitlines() boundary in the Cc category. A lone CR is
        # not a line ending in the Desktop Entry format; it must fail closed.
        data = (
            "[Desktop Entry]\nType=Application\nName=App\rExec=/bin/true\n"
        ).encode("utf-8")
        with self.assertRaisesRegex(MalformedEntryError, "non-printable"):
            parse(data)

    def test_crlf_line_endings_still_parse(self):
        data = (
            "[Desktop Entry]\r\nType=Application\r\nName=App\r\n"
            "Exec=/bin/true\r\n"
        ).encode("utf-8")
        entry = parse(data)
        self.assertEqual(entry.name, "App")
        self.assertEqual(entry.exec, "/bin/true")

    def test_continuation_and_printable_text_still_parse(self):
        data = (
            "[Desktop Entry]\nType=Application\nName=Caf\u00a0App\n"
            "Exec=/usr/bin/app \\\n    --flag\n"
        ).encode("utf-8")
        entry = parse(data)
        self.assertEqual(entry.name, "Caf\u00a0App")
        self.assertEqual(entry.exec_argv(), ["/usr/bin/app", "--flag"])


if __name__ == "__main__":
    unittest.main()
