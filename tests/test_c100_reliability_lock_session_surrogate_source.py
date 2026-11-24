"""Regression: an unpaired-surrogate event source is a structural contract violation.

``SessionEvent`` documents ``LockSessionEventError`` for an invalid event.
A caller-supplied ``source`` containing an unpaired UTF-16 surrogate cannot be
UTF-8 encoded, so its ``MAX_SOURCE_BYTES`` byte length is undefined. Validation
must reject it with ``LockSessionEventError`` rather than leaking the raw
``UnicodeEncodeError`` from ``str.encode``.

Pure in-memory validator tests: no threads, timers, polling, D-Bus or I/O.
"""
import unittest
from typing import Any

from canopy_features.reliability import lock_session_events as lse


def event(**overrides: Any):
    fields: dict[str, Any] = dict(kind="lock", timestamp=0.0, source="logind")
    fields.update(overrides)
    return lse.SessionEvent(**fields)


class LockSessionSurrogateSourceTests(unittest.TestCase):
    def test_unpaired_surrogate_source_raises_domain_error(self):
        bad_sources = (
            "logind\ud800",   # high surrogate at the end
            "\udfff",         # lone low surrogate
            "a\ud800b",       # surrogate in the middle
            "\udc00",         # lone low surrogate as whole source
        )
        for bad in bad_sources:
            with self.subTest(source=repr(bad)):
                with self.assertRaises(lse.LockSessionEventError):
                    event(source=bad)

    def test_raised_error_is_domain_error_not_unicode_encode_error(self):
        with self.assertRaises(lse.LockSessionEventError) as ctx:
            event(source="x\ud800")
        self.assertNotIsInstance(ctx.exception, UnicodeEncodeError)

    def test_surrogate_source_refused_for_every_event_kind(self):
        for kind in sorted(lse.KINDS):
            with self.subTest(kind=kind):
                with self.assertRaises(lse.LockSessionEventError):
                    event(kind=kind, timestamp=1.0, source="bad\ud800")

    def test_source_type_check_still_raises_domain_error(self):
        for bad in (None, 123, b"logind"):
            with self.subTest(source=repr(bad)):
                with self.assertRaises(lse.LockSessionEventError):
                    event(source=bad)

    def test_source_byte_bound_still_enforced(self):
        within = "a" * 64          # MAX_SOURCE_BYTES exactly
        over = "a" * 65            # one byte over
        self.assertEqual(event(source=within).source, within)
        with self.assertRaisesRegex(lse.LockSessionEventError, "source"):
            event(source=over)

    def test_valid_source_and_regex_contract_unchanged(self):
        self.assertEqual(event(source="logind:0").source, "logind:0")
        with self.assertRaises(lse.LockSessionEventError):
            event(source="Bad Source")   # space not in _SOURCE allowlist


if __name__ == "__main__":
    unittest.main()
