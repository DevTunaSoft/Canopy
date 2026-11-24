"""Regression tests for hostile capability values at the metadata boundary.

A ``str`` subclass is still an instance of ``str`` but may be unhashable (or
override comparison), so the ``cap in CAPABILITIES`` membership test and the
duplicate-detection ``set(capabilities)`` can raise a raw ``TypeError`` before
the module's domain error is produced. Hostile-but-bounded metadata must fail
closed with ``PackValidationError`` instead of leaking a built-in exception.
"""

import unittest

from canopy_features.security.pack_manifest_metadata import to_safe_metadata
from tools.check_shell_pack import PackValidationError


def _manifest(capabilities):
    return {
        "manifest_version": 1,
        "id": "com.community.calm.desktop",
        "name": "Calm Desktop",
        "description": "An original Canopy presentation pack",
        "shell_api": 1,
        "kind": "presentation",
        "ui_engine": "qt-qml",
        "entrypoint": "ui/Main.qml",
        "capabilities": capabilities,
        "switch_strategy": "same-session",
        "permissions": [],
    }


class _UnhashableStr(str):
    __hash__ = None


class _HostileEqStr(str):
    def __eq__(self, other):
        raise AssertionError("hostile __eq__ must not be invoked")

    __hash__ = None


class HostileCapabilityTypeTests(unittest.TestCase):
    def assert_fails_closed(self, capabilities):
        with self.assertRaises(PackValidationError):
            to_safe_metadata(_manifest(capabilities))

    def test_unhashable_str_subclass_capability_fails_closed(self):
        self.assert_fails_closed([_UnhashableStr("dock")])

    def test_duplicate_unhashable_str_subclass_capabilities_fail_closed(self):
        # Duplicate capability IDs must also fail closed, not explode while
        # the duplicate guard builds a set.
        self.assert_fails_closed(
            [_UnhashableStr("dock"), _UnhashableStr("dock")]
        )

    def test_hostile_equality_str_subclass_capability_fails_closed(self):
        self.assert_fails_closed([_HostileEqStr("dock")])

    def test_plain_string_capabilities_still_project(self):
        result = to_safe_metadata(_manifest(["dock", "app-launcher"]))
        self.assertEqual(result.capabilities, frozenset({"dock", "app-launcher"}))


if __name__ == "__main__":
    unittest.main()
