"""Offline unit tests for the portal URI-opening policy gate (no Qt runtime)."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canopy_features.apps.safe_uri_open import (
    DEFAULT_ALLOWED_SCHEMES, MAX_URI_BYTES, UriDecision, validate_open_uri,
)

FILE_ALLOWED = frozenset({"file"})


class SafeUriOpenTests(unittest.TestCase):
    def assertRefused(self, uri, reason, schemes=DEFAULT_ALLOWED_SCHEMES):
        decision = validate_open_uri(uri, schemes)
        self.assertIsInstance(decision, UriDecision)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, reason)
        self.assertEqual(decision.normalized, "")
        return decision

    def test_accepts_bounded_common_requests(self):
        cases = (
            "https://example.com/path?q=1#frag",
            "HTTP://Example.com/Path",
            "http://127.0.0.1:8080/status",
            "mailto:user@example.com?subject=Hello%20World",
            "https://example.com/a%2Fb",
        )
        for uri in cases:
            with self.subTest(uri=uri):
                decision = validate_open_uri(uri)
                self.assertTrue(decision.allowed)
                self.assertEqual(decision.reason, "")
                self.assertEqual(decision.scheme, uri.split(":")[0].casefold())
                self.assertEqual(decision.normalized,
                                 decision.scheme + uri[uri.index(":"):])

    def test_rejects_script_schemes_even_when_explicitly_allowed(self):
        for uri in ("javascript:alert(1)",
                    "JavaScript:alert(document.cookie)",
                    "data:text/html,<script>alert(1)</script>",
                    "vbscript:msgbox(1)"):
            with self.subTest(uri=uri):
                self.assertRefused(uri, "scheme_not_allowed")
                self.assertRefused(uri, "scheme_not_allowed",
                                   frozenset({uri.split(":")[0].casefold()}))

    def test_rejects_file_scheme_by_default(self):
        decision = self.assertRefused("file:///etc/passwd", "scheme_not_allowed")
        self.assertEqual(decision.scheme, "file")

    def test_rejects_file_traversal_even_when_file_is_allowed(self):
        for uri in ("file:///home/user/../../etc/shadow",
                    "file:///etc/%2e%2e/passwd",
                    "file:///etc/%252e%252e/passwd"):
            with self.subTest(uri=uri):
                self.assertRefused(uri, "path_traversal", FILE_ALLOWED)
        self.assertRefused(r"file:///C:\Windows\System32\config", "backslash",
                           FILE_ALLOWED)
        self.assertRefused("https://example.com/a/../b", "path_traversal")
        allowed = validate_open_uri("file:///safe/path/note.txt", FILE_ALLOWED)
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.scheme, "file")

    def test_rejects_malformed_requests(self):
        cases = (
            ("", "empty"),
            ("   ", "whitespace"),
            (" https://example.com", "whitespace"),
            ("https://example.com/a b", "whitespace"),
            ("https://example.com\r\nX-Evil: 1", "control_character"),
            ("https://example.com/\x00", "control_character"),
            ("//example.com/path", "missing_scheme"),
            ("../etc/passwd", "missing_scheme"),
            ("ht^tp://example.com", "missing_scheme"),
            ("1http://example.com", "missing_scheme"),
            ("https://example.com/%ZZ", "invalid_percent_encoding"),
            ("https://example.com/%2", "invalid_percent_encoding"),
            ("https://example.com/%", "invalid_percent_encoding"),
            ("https://user:secret@example.com/", "credentials"),
            ("https://example.com:notaport/", "invalid_port"),
            ("https:///path", "invalid_authority"),
            (b"https://example.com", "invalid_type"),
            (None, "invalid_type"),
            (5, "invalid_type"),
            ("\ud800", "invalid_encoding"),
            ("https://example.com/" + "a" * MAX_URI_BYTES, "too_long"),
        )
        for uri, reason in cases:
            with self.subTest(uri=repr(uri)[:48]):
                self.assertRefused(uri, reason)

    def test_allowlist_is_explicit_and_bounded(self):
        self.assertRefused("https://example.com", "scheme_not_allowed",
                           frozenset({"mailto"}))
        for bad in ("https", set(), frozenset(), frozenset({"123"}),
                    frozenset(f"s{i}" for i in range(20))):
            with self.subTest(bad=repr(bad)[:40]):
                with self.assertRaises((TypeError, ValueError)):
                    validate_open_uri("https://example.com", bad)

    def test_decision_is_immutable(self):
        decision = validate_open_uri("https://example.com")
        with self.assertRaises(FrozenInstanceError):
            decision.allowed = False
        self.assertTrue(decision.allowed)

    def test_no_polling_network_or_process_dependencies(self):
        code = (ROOT / "canopy_features" / "apps" /
                "safe_uri_open.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import subprocess", "urlopen",
                          "import requests", "QTimer", "time.sleep", "Thread(",
                          "Popen", "os.system", "while True"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
