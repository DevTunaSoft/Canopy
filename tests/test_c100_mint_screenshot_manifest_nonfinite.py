"""Serialization failures must stay inside the manifest domain-error boundary.

A caller-supplied manifest that cannot be represented as canonical JSON
(non-finite floats, unsupported value/key types, cyclic data) must be refused
with the documented ``ManifestError``. A raw ``json`` ValueError/TypeError
escaping ``serialize`` also escapes ``write_manifest``'s fail contract and
``main``'s ManifestError-only exception handler.
"""
import tempfile
import unittest
from pathlib import Path

from canopy_features.mint import screenshot_capture_manifest as scm


class SerializationBoundaryTests(unittest.TestCase):
    def assertDomainError(self, fn, pattern="not serializable"):
        with self.assertRaisesRegex(scm.ManifestError, pattern):
            fn()
        # ManifestError is a ValueError subclass: require the exact domain
        # type, not a bare json ValueError/TypeError leaking through.
        try:
            fn()
        except scm.ManifestError as exc:
            self.assertIs(type(exc), scm.ManifestError)

    def test_non_finite_floats_are_refused_with_domain_error(self):
        for token in ("nan", "inf", "-inf"):
            with self.subTest(token=token):
                self.assertDomainError(lambda t=token: scm.serialize({"x": float(t)}))

    def test_non_serializable_value_is_refused_with_domain_error(self):
        self.assertDomainError(lambda: scm.serialize({"x": {1, 2}}))

    def test_non_string_key_is_refused_with_domain_error(self):
        self.assertDomainError(lambda: scm.serialize({(1, 2): "v"}))

    def test_cyclic_manifest_is_refused_with_domain_error(self):
        cyclic = {}
        cyclic["self"] = cyclic
        self.assertDomainError(lambda: scm.serialize(cyclic))

    def test_write_manifest_non_finite_fails_closed_without_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "m.json"
            with self.assertRaises(scm.ManifestError):
                scm.write_manifest(target, {"x": float("nan")})
            self.assertFalse(target.exists())

    def test_wrong_top_level_type_still_uses_domain_error(self):
        self.assertDomainError(lambda: scm.serialize(["not", "an", "object"]),
                               pattern="must be an object")

    def test_valid_manifest_still_serializes_deterministically(self):
        first = scm.serialize({"b": 1, "a": [1, 2, None], "s": "é"})
        reordered = scm.serialize({"a": [1, 2, None], "s": "é", "b": 1})
        self.assertEqual(first, reordered)
        self.assertIn(b'"a"', first)
        self.assertEqual(first, scm.serialize({"a": [1, 2, None], "s": "é", "b": 1}))


if __name__ == "__main__":
    unittest.main()
