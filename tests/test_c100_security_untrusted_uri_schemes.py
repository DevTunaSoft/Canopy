"""Offline unit tests for the untrusted URI scheme gate (task c100).

Pure-Python, platform-independent checks. No Qt, no Mint, no process launch,
no network. These tests prove the validator logic, NOT a wired desktop.
"""
import unittest

from canopy_features.security.untrusted_uri_schemes import (
    DEFAULT_ALLOWED_SCHEMES,
    MAX_URI_CHARS,
    UntrustedUriError,
    is_permitted_uri,
    validate_uri_intent,
)


class PermittedSchemeTests(unittest.TestCase):
    def test_default_allowlist_is_conservative(self):
        self.assertEqual(DEFAULT_ALLOWED_SCHEMES,
                         frozenset({"http", "https", "mailto"}))

    def test_https_is_permitted_and_returns_lowercase_scheme(self):
        self.assertEqual(validate_uri_intent("https://example.com/page?q=1"),
                         "https")

    def test_http_and_mailto_are_permitted(self):
        self.assertEqual(validate_uri_intent("http://example.com"), "http")
        self.assertEqual(validate_uri_intent("mailto:user@example.com"),
                         "mailto")

    def test_scheme_case_is_normalised(self):
        self.assertEqual(validate_uri_intent("HTTPS://example.com"), "https")
        self.assertEqual(validate_uri_intent("MaIlTo:user@example.com"),
                         "mailto")

    def test_query_and_fragment_characters_are_allowed(self):
        uri = "https://example.com/a?x=1&y=2#frag%20ment"
        self.assertEqual(validate_uri_intent(uri), "https")

    def test_custom_allowlist_changes_the_decision(self):
        self.assertEqual(validate_uri_intent("ftp://host/x", allowed={"ftp"}),
                         "ftp")
        with self.assertRaises(UntrustedUriError):
            validate_uri_intent("https://example.com", allowed={"ftp"})

    def test_boolean_wrapper_matches_validator(self):
        self.assertTrue(is_permitted_uri("https://example.com"))
        self.assertFalse(is_permitted_uri("javascript:alert(1)"))
        self.assertFalse(is_permitted_uri("https://x\njavascript:alert(1)"))


class JavascriptSchemeTests(unittest.TestCase):
    """Explicitly exercise the javascript scheme and its obfuscations."""

    def test_javascript_is_rejected(self):
        for uri in ("javascript:alert(1)", "JAVASCRIPT:alert(1)",
                    "JavaScript:alert(1)", "javascript:",
                    "javascript:void(0)//https://example.com"):
            with self.subTest(uri=uri):
                with self.assertRaises(UntrustedUriError):
                    validate_uri_intent(uri)

    def test_javascript_with_leading_control_or_space_is_rejected(self):
        for uri in (" javascript:alert(1)", "\tjavascript:alert(1)",
                    "\njavascript:alert(1)", " java\nscript:alert(1)"):
            with self.subTest(uri=uri):
                with self.assertRaises(UntrustedUriError):
                    validate_uri_intent(uri)

    def test_unicode_lookalike_javascript_is_rejected(self):
        # Fullwidth Latin letters and a fullwidth colon must not parse.
        self.assertFalse(is_permitted_uri(
            "\uff4a\uff41\uff56\uff41\uff53\uff43\uff52\uff49\uff50\uff54"
            "\uff1aalert(1)"))

    def test_encoded_colon_does_not_become_a_scheme(self):
        # No literal ':' before the payload means no valid scheme.
        self.assertFalse(is_permitted_uri("javascript%3Aalert(1)"))

    def test_other_dangerous_schemes_are_rejected(self):
        for uri in ("data:text/html,<script>alert(1)</script>",
                    "vbscript:msgbox(1)", "file:///etc/passwd",
                    "about:blank", "chrome://settings"):
            with self.subTest(uri=uri):
                self.assertFalse(is_permitted_uri(uri))


class NewlinePayloadTests(unittest.TestCase):
    """Explicitly exercise CRLF and Unicode newline smuggling."""

    def test_trailing_newline_after_permitted_scheme_is_rejected(self):
        for uri in ("https://example.com\n", "https://example.com\r\n",
                    "https://example.com\njavascript:alert(1)",
                    "https://example.com\r\nSet-Cookie: sid=1"):
            with self.subTest(uri=uri):
                with self.assertRaises(UntrustedUriError):
                    validate_uri_intent(uri)

    def test_leading_newline_is_rejected(self):
        for uri in ("\nhttps://example.com", "\r\nhttps://example.com"):
            with self.subTest(uri=uri):
                self.assertFalse(is_permitted_uri(uri))

    def test_newline_inside_host_is_rejected(self):
        self.assertFalse(is_permitted_uri("https://exa\nmple.com"))

    def test_nul_tab_and_unicode_separators_are_rejected(self):
        for uri in ("https://example.com\x00.evil",
                    "https://example.com\t.evil",
                    "https://example.com\u2028javascript:alert(1)",
                    "https://example.com\u2029x",
                    "https://example.com\u200b.evil"):
            with self.subTest(uri=uri):
                self.assertFalse(is_permitted_uri(uri))


class MalformedIntentTests(unittest.TestCase):
    def test_empty_and_schemeless_uris_are_rejected(self):
        for uri in ("", "example.com/path", "//example.com/path", "/etc/passwd",
                    ":https://example.com"):
            with self.subTest(uri=uri):
                self.assertFalse(is_permitted_uri(uri))

    def test_malformed_scheme_is_rejected(self):
        for uri in ("1http://example.com", "ht tp://example.com",
                    "http+evil://example.com:", "++://example.com",
                    "http@example.com"):
            with self.subTest(uri=uri):
                self.assertFalse(is_permitted_uri(uri))

    def test_non_string_types_are_rejected(self):
        for uri in (None, 123, b"https://example.com", ["https://example.com"]):
            with self.subTest(uri=uri):
                with self.assertRaises(UntrustedUriError):
                    validate_uri_intent(uri)

    def test_oversized_uri_is_rejected(self):
        self.assertFalse(is_permitted_uri("https://example.com/" + "a" * MAX_URI_CHARS))
        self.assertEqual(validate_uri_intent("https://x/" + "a" * 10), "https")

    def test_invalid_allowlist_fails_closed(self):
        for allowed in ("https", ["javascript"], ["https", "bad scheme"],
                        ["https", 5]):
            with self.subTest(allowed=allowed):
                with self.assertRaises(UntrustedUriError):
                    validate_uri_intent("https://example.com", allowed=allowed)

    def test_error_message_does_not_echo_input(self):
        marker = "SECRET_PAYLOAD_MARKER"
        with self.assertRaises(UntrustedUriError) as ctx:
            validate_uri_intent("javascript:" + marker)
        self.assertNotIn(marker, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
