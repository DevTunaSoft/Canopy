"""Tests for the read-only shared-core capability catalog."""
from __future__ import annotations

import sys
import unittest

from canopy_core import capabilities


class CapabilityCatalogTests(unittest.TestCase):
    def test_catalog_is_bounded_and_sorted(self):
        names = capabilities.names()
        self.assertLessEqual(len(names), capabilities.MAX_CAPABILITIES)
        self.assertEqual(names, tuple(sorted(names)))
        self.assertEqual(len(names), len(set(names)))

    def test_describe_does_not_import_feature_modules(self):
        target = "canopy_features.dock.dock_pinned_items"
        sys.modules.pop(target, None)
        described = capabilities.describe("dock.pins.state")
        self.assertFalse(described.visual)
        self.assertEqual(described.module, target)
        self.assertNotIn(target, sys.modules)

    def test_load_returns_real_callable(self):
        function = capabilities.load("launcher.focus.move")
        self.assertTrue(callable(function))
        self.assertEqual(function.__name__, "move")

    def test_load_is_lazy_for_other_entries(self):
        target = "canopy_features.installer.preview_install_plan"
        sys.modules.pop(target, None)
        capabilities.load("dock.running.state")
        self.assertNotIn(target, sys.modules)

    def test_unknown_and_malformed_names_fail_closed(self):
        for name in ("", "unknown.capability", "../etc/passwd",
                     "LAUNCHER.FOCUS.MOVE", None, 42):
            with self.subTest(name=name), self.assertRaises(capabilities.CapabilityError):
                capabilities.describe(name)

    def test_catalog_excludes_visual_presentation_modules(self):
        for described in (capabilities.describe(name) for name in capabilities.names()):
            self.assertFalse(described.visual)
            self.assertNotIn("qml", described.module.lower())
            self.assertNotIn("visual", described.module.lower())

    def test_descriptor_is_immutable(self):
        described = capabilities.describe("security.uri.validate")
        with self.assertRaises(Exception):
            described.area = "visual"


if __name__ == "__main__":
    unittest.main()
