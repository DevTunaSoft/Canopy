"""Regression tests: hostile bytes-like inputs must fail closed, not raise builtins.

``_as_text`` advertises ``LogSizeCapError`` for invalid input types.  A tiny
``bytes`` subclass that overrides ``decode`` is still accepted by the
``isinstance(value, bytes)`` gate, so its forged return value escapes into the
size-cap helpers and leaks a raw ``AttributeError`` / ``UnicodeEncodeError``.
"""
import unittest
from typing import cast

from canopy_features.security import log_size_caps as caps


class BadDecodeBytes(bytes):
    def decode(self, *args, **kwargs) -> str:
        return cast(str, None)


class SurrogateDecodeBytes(bytes):
    def decode(self, *args, **kwargs) -> str:
        return "x\ud800y"


class HostileDiagnosticInputTests(unittest.TestCase):
    def test_bound_diagnostic_rejects_forged_decode_with_domain_error(self):
        with self.assertRaises(caps.LogSizeCapError):
            caps.bound_diagnostic(BadDecodeBytes(b"x"), 100)

    def test_buffer_feed_rejects_forged_decode_with_domain_error(self):
        with self.assertRaises(caps.LogSizeCapError):
            caps.DiagnosticBuffer(64).feed(BadDecodeBytes(b"x"))

    def test_surrogate_returning_decode_cannot_raise_unicode_error(self):
        for call in (
            lambda: caps.bound_diagnostic(SurrogateDecodeBytes(b"x"), 100),
            lambda: caps.DiagnosticBuffer(64).feed(SurrogateDecodeBytes(b"x")),
        ):
            with self.subTest(call=call):
                with self.assertRaises(caps.LogSizeCapError):
                    call()

    def test_plain_bytes_and_str_are_still_accepted(self):
        self.assertEqual(caps.bound_diagnostic(b"ok", 100), "ok")
        buffer = caps.DiagnosticBuffer(64)
        buffer.feed("ok")
        self.assertEqual(buffer.text(), "ok")


if __name__ == "__main__":
    unittest.main()
