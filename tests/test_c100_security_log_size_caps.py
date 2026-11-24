"""Offline unit tests for bounded diagnostic buffers and JSON report output."""
import json
import unittest

from canopy_features.security import log_size_caps as caps


class DiagnosticBoundTests(unittest.TestCase):
    def test_short_text_unchanged(self):
        for value, expected in (("ok", "ok"), (b"bytes", "bytes"),
                                ("naïve ✓", "naïve ✓")):
            with self.subTest(value=value):
                self.assertEqual(caps.bound_diagnostic(value), expected)

    def test_giant_payload_truncated(self):
        output = caps.bound_diagnostic("A" * 2_000_000, 200)
        self.assertLessEqual(len(output.encode("utf-8")), 200)
        self.assertTrue(output.endswith(caps.TRUNCATION_MARKER))
        self.assertEqual(output.count("A"),
                         200 - len(caps.TRUNCATION_MARKER))

    def test_giant_multibyte_payload_keeps_byte_cap(self):
        output = caps.bound_diagnostic("✓" * 100_000, 64)
        self.assertLessEqual(len(output.encode("utf-8")), 64)
        self.assertTrue(output.endswith(caps.TRUNCATION_MARKER))
        self.assertNotIn("\ufffd", output)

    def test_invalid_utf8_bytes_never_raise(self):
        output = caps.bound_diagnostic(b"bad:\xff\xfe\xc3end", 200)
        self.assertIn("\ufffd", output)
        output.encode("utf-8")  # strict round trip: no surrogates

    def test_lone_surrogate_becomes_visible_escape(self):
        output = caps.bound_diagnostic("x\ud800y", 100)
        self.assertNotIn("\ud800", output)
        self.assertIn("\\ud800", output)
        output.encode("utf-8")

    def test_bad_bounds_and_inputs_rejected(self):
        for bad in (0, -1, caps.MAX_DIAGNOSTIC_BUFFER_BYTES + 1,
                    True, 1.5, "10"):
            with self.subTest(bound=bad):
                with self.assertRaises(caps.LogSizeCapError):
                    caps.bound_diagnostic("x", bad)
        with self.assertRaises(caps.LogSizeCapError):
            caps.bound_diagnostic("x", len(caps.TRUNCATION_MARKER))
        for bad in (None, 123, ["x"]):
            with self.subTest(value=bad):
                with self.assertRaises(caps.LogSizeCapError):
                    caps.bound_diagnostic(bad)


class DiagnosticBufferTests(unittest.TestCase):
    def test_retains_recent_bytes_and_counts_drops(self):
        tail = b"0123456789abcdefghijklmnopqrstuvwxyz"
        buffer = caps.DiagnosticBuffer(16)
        buffer.feed(b"old")
        buffer.feed(tail)
        self.assertEqual(buffer.size, 16)
        self.assertEqual(buffer.text(), "old" + tail[-13:].decode("ascii"))
        self.assertEqual(buffer.dropped_bytes, len(tail) - 13)

    def test_full_buffer_replaced_by_newest_data(self):
        buffer = caps.DiagnosticBuffer(8)
        buffer.feed(b"12345678")
        buffer.feed(b"ABCDEFGHIJ")
        self.assertEqual(buffer.text(), "CDEFGHIJ")
        self.assertEqual(buffer.dropped_bytes, 18)

    def test_giant_chunks_and_invalid_unicode_stay_bounded(self):
        buffer = caps.DiagnosticBuffer(64)
        for _ in range(100):
            buffer.feed(b"\xff\xfe" + b"Z" * 100_000)
        self.assertLessEqual(buffer.size, 64)
        self.assertGreater(buffer.dropped_bytes, 0)
        text = buffer.text()
        self.assertLessEqual(len(text), 64)
        text.encode("utf-8")
        buffer.clear()
        self.assertEqual(buffer.size, 0)
        self.assertEqual(buffer.dropped_bytes, 0)
        buffer.feed(b"\xff\xfe\xc3")
        self.assertIn("\ufffd", buffer.text())

    def test_bad_capacity_rejected(self):
        for bad in (0, -1, caps.MAX_DIAGNOSTIC_BUFFER_BYTES + 1, False, 8.0):
            with self.subTest(bound=bad):
                with self.assertRaises(caps.LogSizeCapError):
                    caps.DiagnosticBuffer(bad)


class JsonReportTests(unittest.TestCase):
    def test_report_within_cap_is_deterministic_valid_json(self):
        payload = {"b": 2, "a": [1, True, None, "✓"],
                   "nested": {"z": "end"}}
        serialized = caps.bounded_json_report(payload, 1024)
        self.assertEqual(json.loads(serialized), payload)
        self.assertEqual(serialized, json.dumps(
            payload, sort_keys=True, ensure_ascii=True,
            allow_nan=False, separators=(",", ":")))
        self.assertTrue(serialized.isascii())
        self.assertLessEqual(len(serialized.encode("ascii")), 1024)

    def test_giant_report_fails_closed(self):
        payload = {"blob": "A" * 2_000_000,
                   "items": list(range(100_000))}
        with self.assertRaises(caps.ReportTooLarge) as caught:
            caps.bounded_json_report(payload, 128)
        self.assertIn("128", str(caught.exception))

    def test_invalid_unicode_in_report_is_ascii_escaped(self):
        payload = {"weird": "\ud800\udcff"}
        serialized = caps.bounded_json_report(payload, 256)
        self.assertTrue(serialized.isascii())
        self.assertIn("\\ud800", serialized)
        self.assertIn("\\udcff", serialized)
        self.assertLessEqual(len(serialized.encode("ascii")), 256)
        self.assertEqual(json.loads(serialized)["weird"], "\U000100ff")

    def test_non_finite_and_cyclic_payloads_rejected(self):
        with self.assertRaises(caps.LogSizeCapError):
            caps.bounded_json_report({"x": float("nan")})
        cyclic = {}
        cyclic["self"] = cyclic
        with self.assertRaises(caps.LogSizeCapError):
            caps.bounded_json_report(cyclic)

    def test_exact_cap_boundary(self):
        payload = {"a": 1}
        exact = json.dumps(payload, sort_keys=True, ensure_ascii=True,
                           allow_nan=False, separators=(",", ":"))
        self.assertEqual(caps.bounded_json_report(payload, len(exact)), exact)
        with self.assertRaises(caps.ReportTooLarge):
            caps.bounded_json_report(payload, len(exact) - 1)

    def test_iterencode_chunks_are_ascii_by_contract(self):
        # bounded_json_report counts chunk bytes with len(chunk); that is only
        # correct because ensure_ascii=True makes every chunk ASCII.
        payload = {"unicode": "✓ café", "surrogate": "\ud800\udcff",
                   "escape": "line\nquote\"slash\\", "nested": [1, True, None]}
        encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=True,
                                   allow_nan=False, separators=(",", ":"))
        chunks = tuple(encoder.iterencode(payload))
        self.assertTrue(chunks)
        for chunk in chunks:
            with self.subTest(chunk=chunk[:24]):
                self.assertTrue(chunk.isascii())
                self.assertEqual(len(chunk), len(chunk.encode("ascii")))

    def test_cap_boundary_is_byte_exact_with_escaped_unicode(self):
        payload = {"k": "✓" * 100}
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                allow_nan=False, separators=(",", ":"))
        self.assertTrue(serialized.isascii())
        self.assertEqual(caps.bounded_json_report(payload, len(serialized)), serialized)
        with self.assertRaises(caps.ReportTooLarge):
            caps.bounded_json_report(payload, len(serialized) - 1)

    def test_bad_report_cap_rejected(self):
        for bad in (0, -1, caps.MAX_REPORT_BYTES + 1, True, 2.5, "64"):
            with self.subTest(bound=bad):
                with self.assertRaises(caps.LogSizeCapError):
                    caps.bounded_json_report({}, bad)


if __name__ == "__main__":
    unittest.main()
