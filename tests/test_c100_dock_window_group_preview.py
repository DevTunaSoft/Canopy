"""Tests for the pure, no-echo dock window-group preview.

Run: python -m unittest tests.test_c100_dock_window_group_preview -v
No Qt runtime, window manager, geometry, D-Bus or desktop is involved.
"""
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from canopy_features.dock import window_group_preview as preview_mod
from canopy_features.dock.window_group_preview import (
    FIXED_CLAIMS,
    REASON_INVALID_INPUT,
    REASON_OK,
    REASON_SOURCE_DISAGREEMENT,
    REASON_UNPINNED_GROUP,
    STATUS_DENIED,
    STATUS_READY,
    WindowGroupPreview,
    compose_window_group_preview,
)
from canopy_features.dock.dock_pinned_items import PinnedItems
from canopy_features.dock.window_grouping import (
    GroupingResult,
    WindowGroup,
    WindowRecord,
)

TRUSTED = {
    "org.example.Files.desktop": "Files",
    "org.example.Browser.desktop": "Browser",
}
PINNED = PinnedItems(items=("Files", "Browser", "Terminal"))
WINDOWS = (
    WindowRecord(window_id=1001, desktop_id="org.example.Files.desktop"),
    WindowRecord(window_id=1002, desktop_id="org.example.Files.desktop"),
    WindowRecord(window_id=2001, desktop_id="org.example.Browser.desktop"),
    WindowRecord(window_id=9999, desktop_id="org.example.Unknown.desktop"),
    WindowRecord(window_id=1001, desktop_id="org.example.Files.desktop"),
)


def compose(windows=WINDOWS, trusted_map=TRUSTED, pinned=PINNED, **kwargs):
    return compose_window_group_preview(windows, trusted_map, pinned, **kwargs)


class ApprovedTests(unittest.TestCase):
    def test_constants_are_fixed_negative_claims(self):
        self.assertEqual(STATUS_READY, "READY")
        self.assertEqual(STATUS_DENIED, "DENIED")
        self.assertEqual(REASON_OK, "ok")
        self.assertIsInstance(FIXED_CLAIMS, tuple)
        self.assertTrue(FIXED_CLAIMS)
        self.assertTrue(all(type(c) is str for c in FIXED_CLAIMS))
        for claim in ("no_window_ids_echoed", "no_desktop_ids_echoed",
                      "no_labels_echoed", "no_geometry_read",
                      "no_process_launched"):
            with self.subTest(claim=claim):
                self.assertIn(claim, FIXED_CLAIMS)

    def test_approved_counts_only(self):
        result = compose()
        self.assertEqual(result, WindowGroupPreview(
            STATUS_READY, REASON_OK, group_count=2, window_count=3,
            unmapped_count=1, duplicate_count=1, claims=FIXED_CLAIMS))
        self.assertTrue(result.ready)

    def test_no_window_desktop_or_label_values_are_echoed(self):
        payload = repr(compose().to_dict())
        for secret in ("1001", "1002", "2001", "9999",
                       "org.example.Files.desktop", "org.example.Unknown.desktop",
                       "Files", "Browser"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, payload)

    def test_empty_windows_is_approved_with_zero_counts(self):
        result = compose(windows=())
        self.assertEqual(result.group_count, 0)
        self.assertEqual(result.window_count, 0)
        self.assertEqual(result.claims, FIXED_CLAIMS)

    def test_to_dict_shape(self):
        self.assertEqual(set(compose().to_dict()), {
            "status", "reason", "group_count", "window_count",
            "unmapped_count", "duplicate_count", "claims"})

    def test_record_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            compose().group_count = 99

    def test_no_geometry_module_import(self):
        with open(preview_mod.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("display_geometry", source)
        self.assertNotIn("subprocess", source)


class DenialTests(unittest.TestCase):
    def assert_terse_denial(self, result, reason):
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, reason)
        self.assertFalse(result.ready)
        self.assertEqual(result.group_count, 0)
        self.assertEqual(result.window_count, 0)
        self.assertEqual(result.unmapped_count, 0)
        self.assertEqual(result.duplicate_count, 0)
        self.assertEqual(result.claims, ())

    def test_unpinned_group_is_denied_without_echo(self):
        result = compose(pinned=PinnedItems(items=("Files",)))
        self.assert_terse_denial(result, REASON_UNPINNED_GROUP)
        self.assertNotIn("Browser", repr(result.to_dict()))

    def test_wrong_pinned_type_is_denied(self):
        self.assert_terse_denial(compose(pinned=("Files",)), REASON_INVALID_INPUT)

    def test_hostile_pinned_label_is_denied_without_raw_exception(self):
        class HostilePinnedLabel:
            """A bounded pinned-snapshot entry whose comparison always raises."""

            def __eq__(self, other):
                raise RuntimeError("SYNTHETIC hostile pinned label")

        bounded = PinnedItems(items=(HostilePinnedLabel(), "Files"))  # type: ignore[arg-type]
        try:
            result = compose(pinned=bounded)
        except Exception as exc:
            self.fail("compose leaked a raw exception: %r" % (exc,))
        self.assert_terse_denial(result, REASON_INVALID_INPUT)
        self.assertNotIn("SYNTHETIC", repr(result.to_dict()))

    def test_grouping_failure_is_denied_without_echo(self):
        bad = (WindowRecord(window_id=["unhashable"],
                            desktop_id="org.example.Files.desktop"),)
        result = compose(windows=bad)
        self.assert_terse_denial(result, REASON_INVALID_INPUT)
        self.assertNotIn("unhashable", repr(result.to_dict()))

    def test_source_disagreement_is_fault_injected(self):
        malformed = GroupingResult(groups=("SECRET-GROUP",),
                                   unmapped=(), duplicates=())
        with patch.object(preview_mod, "group_windows_by_desktop_id",
                          return_value=malformed):
            result = compose()
        self.assert_terse_denial(result, REASON_SOURCE_DISAGREEMENT)
        self.assertNotIn("SECRET-GROUP", repr(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
