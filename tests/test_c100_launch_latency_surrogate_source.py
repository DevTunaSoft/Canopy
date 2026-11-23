"""Regression: unpaired-surrogate marker source is a structural contract violation.

``summarize`` documents that structural contract violations raise
``LatencyError``. A caller-supplied ``source`` containing an unpaired UTF-16
surrogate cannot be UTF-8 encoded, so its ``MAX_SOURCE_BYTES`` byte length is
undefined; ``_check_contract`` must reject it with ``LatencyError`` rather
than leaking ``UnicodeEncodeError``.

Pure in-memory validator tests: no process launch, no clock read, no I/O.
"""
import unittest

from canopy_features.performance import launch_latency as ll


def sample(**overrides):
    fields = dict(
        kind="cold",
        start_ns=0,
        ready_ns=1_000_000,
        source="measure_qt:CANOPY_CLASSIC_WINDOW_READY",
    )
    fields.update(overrides)
    return ll.LaunchSample(**fields)


class LaunchLatencySurrogateSourceTests(unittest.TestCase):
    def test_unpaired_surrogate_source_raises_latency_error(self):
        bad_sources = (
            "measure_qt:BAD\ud800",   # high surrogate at the end
            "\udfff",                 # lone low surrogate
            "a\ud800b",               # surrogate in the middle
        )
        for bad in bad_sources:
            with self.subTest(source=repr(bad)):
                with self.assertRaises(ll.LatencyError):
                    ll.summarize([sample(source=bad)])

    def test_raised_error_is_latency_error_not_unicode_encode_error(self):
        with self.assertRaises(ll.LatencyError) as ctx:
            ll.summarize([sample(source="x\ud800")])
        self.assertNotIsInstance(ctx.exception, UnicodeEncodeError)

    def test_surrogate_in_batch_with_valid_samples_is_refused(self):
        with self.assertRaises(ll.LatencyError):
            ll.summarize([
                sample(kind="warm", source="ok"),
                sample(source="bad\ud800"),
            ])

    def test_valid_supplementary_unicode_source_is_accepted(self):
        # A real non-BMP code point encodes to 4 UTF-8 bytes and is valid.
        result = ll.summarize([sample(source="measure:\U0001F600")])
        self.assertEqual(result["cold"]["count"], 1)
        self.assertEqual(result["provenance"]["excluded_count"], 0)

    def test_valid_multibyte_source_still_accepted(self):
        src = "measure_qt:\u00e9"  # 2-byte UTF-8 char, well within the bound
        result = ll.summarize([sample(source=src)])
        self.assertEqual(result["provenance"]["sources"], [src])
        self.assertEqual(result["cold"]["count"], 1)

    def test_source_byte_length_bound_still_enforced(self):
        # 64 two-byte chars == MAX_SOURCE_BYTES exactly; 65 exceeds it.
        within = "\u00e9" * (ll.MAX_SOURCE_BYTES // 2)
        over = "\u00e9" * (ll.MAX_SOURCE_BYTES // 2 + 1)
        self.assertEqual(ll.summarize([sample(source=within)])["cold"]["count"], 1)
        with self.assertRaisesRegex(ll.LatencyError, "source"):
            ll.summarize([sample(source=over)])


if __name__ == "__main__":
    unittest.main()
