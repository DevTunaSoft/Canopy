"""Regression: surrogate-bearing vminfo text must raise the domain error.

``parse_vminfo`` measures its byte bound with ``text.encode("utf-8")``. An
unpaired surrogate cannot be encoded, so previously a caller-supplied snapshot
leaked a raw ``UnicodeEncodeError`` instead of the documented ``EvidenceError``.
These tests pin the fail-closed contract at each public entry point and keep
the byte bound and benign non-ASCII behaviour as controls.
"""
import unittest

from canopy_features.mint.vbox_guest_readiness import (
    EvidenceError, MAX_INPUT_BYTES, build_normalized_evidence, normalize_vm,
    parse_vminfo,
)

# Minimal valid preflight used only to reach build_normalized_evidence.
_PREFLIGHT = {
    "schema_version": 1,
    "probe_only": True,
    "status": "READY_FOR_TESTS",
    "mint_identified": True,
    "version_id": "22.3",
    "cinnamon_identified": True,
    "graphical_display_present": True,
    "session_type": "x11",
    "commands_present": {},
    "blockers": [],
}

SURROGATES = (
    "a\ud800b",       # embedded high surrogate
    "\udfff",          # lone low surrogate
    "name\udcffx",     # embedded low surrogate
    "\ud800\udfff",    # surrogate pair used as two lone scalars (ill-formed)
)


class VminfoSurrogateTests(unittest.TestCase):
    def assert_domain_error(self, fn):
        """The documented domain error, never a raw UnicodeEncodeError."""
        with self.assertRaises(EvidenceError):
            fn()

    def test_parse_vminfo_refuses_surrogate_text(self):
        for text in SURROGATES:
            with self.subTest(text=ascii(text)):
                self.assert_domain_error(lambda: parse_vminfo(text))

    def test_normalize_vm_refuses_surrogate_snapshot(self):
        for text in SURROGATES:
            with self.subTest(text=ascii(text)):
                self.assert_domain_error(lambda: normalize_vm(vminfo_text=text))

    def test_build_evidence_refuses_surrogate_snapshot(self):
        for text in SURROGATES:
            with self.subTest(text=ascii(text)):
                self.assert_domain_error(
                    lambda: build_normalized_evidence(
                        _PREFLIGHT, vminfo_text=text))

    def test_benign_non_ascii_snapshot_still_parses(self):
        # A supplementary (non-BMP) code point is valid UTF-8 and must work.
        text = 'name="mint-\U0001f600"\nVMState="running"\n'
        parsed = parse_vminfo(text)
        self.assertEqual(parsed["name"], "mint-\U0001f600")
        self.assertEqual(parsed["VMState"], "running")

    def test_byte_bound_still_enforced_on_multibyte_text(self):
        # 2 bytes per char: this exceeds MAX_INPUT_BYTES when UTF-8 encoded.
        text = "\u00e9" * (MAX_INPUT_BYTES // 2 + 1)
        self.assert_domain_error(lambda: parse_vminfo(text))

    def test_non_string_input_still_refused(self):
        for bad in (123, b"name=x", ["name=x"]):
            with self.subTest(bad=bad):
                self.assert_domain_error(lambda: parse_vminfo(bad))


if __name__ == "__main__":
    unittest.main()
