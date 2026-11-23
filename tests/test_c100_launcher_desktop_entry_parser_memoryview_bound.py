"""Regression tests: desktop entry size bound counts bytes, not elements.

A memoryview over a non-byte format reports len() in elements. parse() must
enforce ``max_bytes`` against the real byte length (nbytes / bytes(data)), or
a caller-supplied memoryview can smuggle an oversized entry past the bound.

Controls prove the plain-bytes and byte-format-memoryview paths were and remain
correct; the memoryview cases are the RED regression.
"""
import array
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canopy_features.launcher.desktop_entry_parser import (  # noqa: E402
    MalformedEntryError,
    parse,
)

SAMPLE = (b"[Desktop Entry]\nType=Application\nName=App\n"
          b"Exec=/usr/bin/true\n")


def bytes_payload(total):
    """A valid entry padded with a comment to exactly ``total`` bytes."""
    assert total % 8 == 0 and total >= len(SAMPLE) + 2
    return SAMPLE + b"#" + b"x" * (total - len(SAMPLE) - 2) + b"\n"


def element_memoryview(total):
    """An 8-byte-element memoryview whose byte length is ``total``."""
    return memoryview(array.array("Q", bytes_payload(total)))


class MemoryviewByteBoundTests(unittest.TestCase):
    def test_nonbyte_memoryview_over_limit_is_refused(self):
        # 200000 bytes, but len(memoryview) is only 25000 elements. Under the
        # default 64 KiB byte limit this must be refused, not parsed.
        view = element_memoryview(200_000)
        self.assertEqual(len(view), 25_000)
        self.assertEqual(view.nbytes, 200_000)
        with self.assertRaisesRegex(MalformedEntryError, "size limit"):
            parse(view)

    def test_nonbyte_memoryview_just_over_explicit_limit_is_refused(self):
        view = element_memoryview(1032)
        self.assertEqual(view.nbytes, 1032)
        with self.assertRaisesRegex(MalformedEntryError, "size limit"):
            parse(view, max_bytes=1025)

    # --- negative controls: these pass on unfixed code too ---

    def test_plain_bytes_over_limit_is_refused(self):
        with self.assertRaisesRegex(MalformedEntryError, "size limit"):
            parse(bytes_payload(200_000))

    def test_byte_format_memoryview_over_limit_is_refused(self):
        view = memoryview(bytes_payload(200_000))
        self.assertEqual(len(view), view.nbytes)
        with self.assertRaisesRegex(MalformedEntryError, "size limit"):
            parse(view)

    def test_small_nonbyte_memoryview_is_accepted(self):
        entry = parse(element_memoryview(1024))
        self.assertEqual(entry.name, "App")

    def test_nonbyte_memoryview_at_exact_limit_is_accepted(self):
        view = element_memoryview(1024)
        self.assertEqual(view.nbytes, 1024)
        entry = parse(view, max_bytes=1024)
        self.assertEqual(entry.type, "Application")

    def test_bytearray_and_bytes_forms_still_parse(self):
        self.assertEqual(parse(bytearray(SAMPLE)).name, "App")
        self.assertEqual(parse(memoryview(bytearray(SAMPLE))).name, "App")


class LimitValidationTests(unittest.TestCase):
    def test_invalid_max_bytes_is_refused(self):
        for bad in (True, False, 0, -1, 1.5, float("inf"), "1024", None):
            with self.subTest(bad=bad):
                with self.assertRaises(MalformedEntryError):
                    parse(SAMPLE, max_bytes=bad)

    def test_explicit_positive_int_limit_still_works(self):
        self.assertEqual(parse(SAMPLE, max_bytes=len(SAMPLE)).name, "App")


if __name__ == "__main__":
    unittest.main()
