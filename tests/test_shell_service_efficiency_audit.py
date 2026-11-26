"""Efficiency-audit regression tests for shell-owned services.

The confirmed defect is an allocation-order bug in the untrusted Shell Pack
metadata gate: to_safe_metadata() materialized the whole caller-supplied
mapping with dict() before _scan() applied its documented MAX_FIELDS bound.
A hostile mapping could therefore force O(n) copying before rejection.
All probes here are finite and deterministic: no unbounded iterables, no
timing thresholds and no runtime RSS claims.
"""

from collections.abc import Mapping
import unittest

from canopy_features.security.pack_manifest_metadata import (
    MAX_FIELDS,
    SafePackMetadata,
    to_safe_metadata,
)
from tools.check_shell_pack import PackValidationError


def valid_manifest():
    """Safe, schema-shaped untrusted metadata used for the controls."""
    return {
        "manifest_version": 1,
        "id": "com.community.calm.desktop",
        "name": "Calm Desktop",
        "description": "An original Canopy presentation pack",
        "shell_api": 1,
        "kind": "presentation",
        "ui_engine": "qt-qml",
        "entrypoint": "ui/Main.qml",
        "capabilities": ["dock", "app-launcher"],
        "switch_strategy": "same-session",
        "permissions": [],
    }


class CountingMapping(Mapping):
    """Bounded mapping that records how many items a caller consumes."""

    def __init__(self, size):
        self._size = size
        self.consumed = 0

    def __len__(self):
        return self._size

    def __iter__(self):
        for index in range(self._size):
            self.consumed += 1
            yield "field_%04d" % index, "v"

    def __getitem__(self, key):
        return "v"


class OversizedMappingPreBoundTests(unittest.TestCase):
    def test_oversized_mapping_is_rejected_before_items_are_consumed(self):
        # RED control: base code calls dict(manifest) first, consuming all
        # MAX_FIELDS+1 entries before _scan rejects the size. A bounded gate
        # must reject on len() alone and consume none.
        hostile = CountingMapping(MAX_FIELDS + 1)
        with self.assertRaises(PackValidationError):
            to_safe_metadata(hostile)
        self.assertEqual(hostile.consumed, 0)

    def test_plain_oversized_dict_keeps_the_same_domain_error(self):
        hostile = valid_manifest()
        for index in range(MAX_FIELDS + 1):
            hostile["extra_%04d" % index] = "v"
        with self.assertRaisesRegex(PackValidationError, "too many fields"):
            to_safe_metadata(hostile)

    def test_exactly_at_bound_still_projects(self):
        # Negative control against a fix that simply refuses large inputs:
        # a safe mapping with exactly MAX_FIELDS fields must still project.
        manifest = valid_manifest()
        for index in range(MAX_FIELDS - len(manifest)):
            manifest["extra_%04d" % index] = "v"
        self.assertEqual(len(manifest), MAX_FIELDS)
        result = to_safe_metadata(manifest)
        self.assertIsInstance(result, SafePackMetadata)
        self.assertEqual(result.pack_id, "com.community.calm.desktop")

    def test_oversized_nested_mapping_still_rejected_by_scan(self):
        # The original depth bound must remain active; the new top-level
        # pre-bound is not a replacement for _scan's recursive check.
        manifest = valid_manifest()
        manifest["extra_nested"] = {
            "child_%04d" % index: "v" for index in range(MAX_FIELDS + 1)
        }
        with self.assertRaisesRegex(PackValidationError, "too many fields"):
            to_safe_metadata(manifest)

    def test_hostile_length_probe_fails_closed(self):
        # The fix adds a len() call on untrusted input; a hostile __len__
        # must not leak a built-in ValueError past the domain boundary.
        class HostileLength(Mapping):
            def __len__(self):
                raise ValueError("hostile len")

            def __iter__(self):
                return iter(())

            def __getitem__(self, key):
                raise KeyError(key)

        with self.assertRaises(PackValidationError):
            to_safe_metadata(HostileLength())


if __name__ == "__main__":
    unittest.main()
