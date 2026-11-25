"""Offline unit tests for the freedesktop Desktop Entry parser.

These tests need no Qt, GIO, Linux session or network. They exercise valid
metadata plus malformed input, duplicates and invalid encoding.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canopy_features.launcher.desktop_entry_parser import (
    DEFAULT_MAX_BYTES,
    DesktopEntry,
    DesktopEntryError,
    DuplicateKeyError,
    InvalidEncodingError,
    MalformedEntryError,
    parse,
    parse_file,
)


SAMPLE = (
    b"[Desktop Entry]\n"
    b"Type=Application\n"
    b"Version=1.0\n"
    b"Name=Canopy Files\n"
    b"Name[fr]=Fichiers Canopy\n"
    b"Exec=/usr/bin/canopy-files --open %f\n"
    b"Icon=canopy-files\n"
    b"Terminal=false\n"
    b"NoDisplay=false\n"
    b"Hidden=false\n"
    b"Categories=Utility;FileManager;\n"
)


def desktop(exec_line: str) -> bytes:
    return (
        "[Desktop Entry]\nType=Application\nName=App\n" + exec_line + "\n"
    ).encode("utf-8")


class DesktopEntryParserTests(unittest.TestCase):
    def test_valid_application_metadata(self):
        entry = parse(SAMPLE)
        self.assertEqual(entry.type, "Application")
        self.assertEqual(entry.values["Version"], "1.0")
        self.assertEqual(entry.name, "Canopy Files")
        self.assertEqual(entry.exec, "/usr/bin/canopy-files --open %f")
        self.assertEqual(entry.icon, "canopy-files")
        self.assertFalse(entry.terminal)
        self.assertFalse(entry.no_display)
        self.assertFalse(entry.hidden)
        self.assertEqual(entry.categories, ("Utility", "FileManager"))
        self.assertEqual(entry.exec_argv(),
                         ["/usr/bin/canopy-files", "--open", "%f"])

    def test_localized_name_does_not_replace_base_name(self):
        entry = parse(SAMPLE)
        self.assertEqual(entry.name, "Canopy Files")
        self.assertEqual(entry.localized_name("fr"), "Fichiers Canopy")
        self.assertEqual(entry.localized_name("de"), "")
        self.assertEqual(entry.localized["Name"]["fr"], "Fichiers Canopy")

    def test_utf8_bom_is_accepted(self):
        self.assertEqual(parse(b"\xef\xbb\xbf" + SAMPLE).name, "Canopy Files")

    def test_non_ascii_utf8_name(self):
        data = SAMPLE.replace(b"Name=Canopy Files", "Name=Café — Canopy".encode("utf-8"))
        self.assertEqual(parse(data).name, "Café — Canopy")

    def test_exec_quotes_and_escapes_are_split_without_a_shell(self):
        data = desktop('Exec=/usr/bin/app a\\ b "c d" say\\"hi\\" "%f"')
        self.assertEqual(parse(data).exec_argv(),
                         ["/usr/bin/app", "a b", "c d", 'say"hi"', "%f"])

    def test_exec_unterminated_quote_is_malformed(self):
        with self.assertRaisesRegex(MalformedEntryError, "quote"):
            parse(desktop('Exec=/usr/bin/app "oops'))

    def test_exec_dangling_escape_is_malformed(self):
        # A trailing backslash in a file is a line continuation, so drive the
        # tokenizer directly for this case.
        entry = DesktopEntry(
            values={"Type": "Application", "Name": "App",
                    "Exec": "/usr/bin/app oops\\"},
            localized={},
        )
        with self.assertRaisesRegex(MalformedEntryError, "escape"):
            entry.exec_argv()

    def test_line_continuation_joins_exec(self):
        data = ("[Desktop Entry]\nType=Application\nName=App\n"
                "Exec=/usr/bin/app \\\n    --flag\n").encode("utf-8")
        self.assertEqual(parse(data).exec_argv(), ["/usr/bin/app", "--flag"])

    def test_missing_group_is_malformed(self):
        with self.assertRaisesRegex(MalformedEntryError, "outside any group"):
            parse(b"Name=App\n")

    def test_line_without_equals_is_malformed(self):
        with self.assertRaisesRegex(MalformedEntryError, "without '='"):
            parse(SAMPLE + b"BrokenLine\n")

    def test_invalid_group_header_is_malformed(self):
        with self.assertRaisesRegex(MalformedEntryError, "group header"):
            parse(b"[]\n" + SAMPLE)

    def test_missing_required_fields_are_malformed(self):
        for key in ("Type", "Name", "Exec"):
            with self.subTest(key=key):
                data = b"".join(
                    line for line in SAMPLE.splitlines(keepends=True)
                    if not line.startswith(key.encode("utf-8") + b"=")
                )
                with self.assertRaisesRegex(MalformedEntryError, "missing " + key):
                    parse(data)

    def test_non_application_type_is_rejected_by_default(self):
        data = SAMPLE.replace(b"Type=Application", b"Type=Link")
        with self.assertRaisesRegex(MalformedEntryError, "Application"):
            parse(data)
        self.assertEqual(parse(data, require_application=False).type, "Link")

    def test_invalid_boolean_is_malformed(self):
        for key in ("Terminal", "NoDisplay", "Hidden"):
            with self.subTest(key=key):
                data = SAMPLE.replace(key.encode("utf-8") + b"=false",
                                      key.encode("utf-8") + b"=yes")
                with self.assertRaisesRegex(MalformedEntryError, "boolean"):
                    parse(data)

    def test_duplicate_key_is_rejected(self):
        for key in (b"Name", b"Exec", b"Icon"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(DuplicateKeyError, "duplicate key"):
                    parse(SAMPLE + key + b"=Again\n")

    def test_duplicate_localized_key_is_rejected(self):
        with self.assertRaisesRegex(DuplicateKeyError, "duplicate key"):
            parse(SAMPLE + b"Name[fr]=Encore\n")

    def test_duplicate_group_is_malformed(self):
        with self.assertRaisesRegex(MalformedEntryError, "duplicate group"):
            parse(SAMPLE + b"[Desktop Entry]\n")

    def test_other_groups_and_comments_are_ignored(self):
        data = SAMPLE + (
            b"\n# a comment\n"
            b"[Desktop Action extra]\n"
            b"Name=Other Name\n"
            b"Exec=/bin/other\n"
        )
        entry = parse(data)
        self.assertEqual(entry.name, "Canopy Files")
        self.assertEqual(entry.exec, "/usr/bin/canopy-files --open %f")

    def test_invalid_utf8_byte_is_rejected(self):
        with self.assertRaises(InvalidEncodingError):
            parse(SAMPLE.replace(b"Name=Canopy Files", b"Name=\xff"))

    def test_utf16_input_is_rejected(self):
        with self.assertRaises(InvalidEncodingError):
            parse(SAMPLE.decode("utf-8").encode("utf-16"))

    def test_oversized_input_is_rejected(self):
        with self.assertRaisesRegex(MalformedEntryError, "size limit"):
            parse(SAMPLE, max_bytes=10)
        self.assertLess(len(SAMPLE), DEFAULT_MAX_BYTES)

    def test_parse_file_is_bounded_and_reads_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "app.desktop"
            path.write_bytes(SAMPLE)
            self.assertEqual(parse_file(path).name, "Canopy Files")
            with self.assertRaisesRegex(MalformedEntryError, "size limit"):
                parse_file(path, max_bytes=10)

    def test_parsing_never_executes_exec(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "marker"
            data = desktop("Exec=/usr/bin/touch " + marker.as_posix())
            entry = parse(data)
            self.assertEqual(entry.exec_argv()[1], marker.as_posix())
            self.assertFalse(marker.exists())

    def test_errors_share_a_value_error_base(self):
        for error in (DesktopEntryError, DuplicateKeyError,
                      InvalidEncodingError, MalformedEntryError):
            with self.subTest(error=error.__name__):
                self.assertTrue(issubclass(error, DesktopEntryError))
        self.assertTrue(issubclass(DesktopEntryError, ValueError))


if __name__ == "__main__":
    unittest.main()
