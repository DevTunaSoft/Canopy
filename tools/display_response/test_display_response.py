"""Targeted pure-Python checks for the M4 native display-response seam.

SYNTHETIC only: no Qt, no compositor, no monitor, no service, no I/O outside
caller-supplied text and no native runtime claim. Kept beside the tool because
the repository's Foundation CI discovers only ``tests/``; this file is run
explicitly with PYTHONPATH pinned to the worktree root.
"""
import hashlib
import unittest

from canopy_features.dock.display_change_response import (
    KIND_HOLD, KIND_NO_OP, DisplayChangeResponse,
)
from canopy_features.dock.geometry import (
    APPROVED, APPROVED_DOCK_GEOMETRY, GeometryContractError,
    assert_approved, geometry_status, parse_theme_geometry,
)


APPROVED_QML = """\
import QtQuick
Item {
    readonly property int barHeight: 32
    readonly property int dockSize: 96
    readonly property int dockPadding: 14
    readonly property int dockSpacing: 7
}
"""


class ApprovedGeometryTests(unittest.TestCase):
    def test_approved_tuple_and_fingerprint_are_stable(self):
        self.assertEqual(APPROVED_DOCK_GEOMETRY, (32, 96, 14, 7))
        self.assertEqual(APPROVED.as_tuple(), APPROVED_DOCK_GEOMETRY)
        self.assertEqual(
            APPROVED.fingerprint(),
            hashlib.sha256(b"32/96/14/7").hexdigest(),
        )
        self.assertIs(assert_approved(APPROVED), APPROVED)

    def test_parse_and_status_never_edit_supplied_text(self):
        status = geometry_status(APPROVED_QML)
        self.assertTrue(status.matches_approved)
        self.assertEqual(status.observed, (32, 96, 14, 7))
        self.assertEqual(status.source_chars, len(APPROVED_QML))
        old = APPROVED_QML.replace("dockSize: 96", "dockSize: 88")
        self.assertFalse(geometry_status(old).matches_approved)

    def test_hostile_geometry_text_fails_closed(self):
        hostile = (
            None, True, 42, APPROVED_QML + "\nreadonly property int dockSize: 96\n",
            APPROVED_QML.replace("dockSize: 96", "dockSize: 100000"),
            APPROVED_QML.replace("dockSpacing: 7", "dockSpacing: -1"),
            "x" * 2_000_001,
        )
        for value in hostile:
            with self.subTest(value=repr(value)[:50]):
                with self.assertRaises(GeometryContractError):
                    parse_theme_geometry(value)
        with self.assertRaises(GeometryContractError):
            assert_approved(None)


class NativePayloadTests(unittest.TestCase):
    def test_wrong_container_types_are_held_not_raised(self):
        response = DisplayChangeResponse()
        hostile = (
            None, True, 42, "kscreen.configChanged", object(),
            {"source": frozenset({"kscreen.configChanged"})},
            {"source": ["kscreen.configChanged"]},
            {"source": "kscreen.configChanged", "outputs": "eDP-1"},
            {"source": "kscreen.configChanged", "outputs": iter(())},
            {"source": "kscreen.configChanged", "outputs": [
                {"connector": "eDP-1", "width": True, "height": 1080,
                 "scale": 1.0, "primary": True}]},
            {"source": "qt.logicalDpiChanged", "connector": "eDP-1",
             "width": 1920, "height": 1080, "scale": float("nan")},
            {"source": "kscreen.configChanged", "outputs": [], "extra": 1},
        )
        for value in hostile:
            with self.subTest(value=repr(value)[:60]):
                plan = response.handle_native_change(value)
                self.assertEqual(plan.kind, KIND_HOLD)
                self.assertEqual(plan.reason, "invalid_event")
                self.assertEqual(plan.size, (1200, 750))

    def test_repeated_snapshot_emits_one_relayout_only(self):
        response = DisplayChangeResponse()
        seen = []
        response.subscribe(seen.append)
        payload = {
            "source": "kscreen.configChanged",
            "outputs": [{"connector": "eDP-1", "width": 1920,
                         "height": 1080, "scale": 1.0, "primary": True}],
        }
        first = response.handle_native_change(payload)
        second = response.handle_native_change(payload)
        self.assertEqual(first.kind, "relayout")
        self.assertEqual(second.kind, KIND_NO_OP)
        self.assertEqual(second.reason, "unchanged")
        self.assertEqual(len(seen), 1)

    def test_secondary_detach_is_relayout_not_desktop_suspend(self):
        response = DisplayChangeResponse()
        base = {"connector": "eDP-1", "width": 1920, "height": 1080,
                "scale": 1.0, "primary": True}
        second = {"connector": "HDMI-1", "width": 1920, "height": 1080,
                  "scale": 1.0, "primary": False}
        response.handle_native_change(
            {"source": "kscreen.configChanged", "outputs": [base, second]})
        plan = response.handle_native_change(
            {"source": "kscreen.configChanged", "outputs": [base]})
        self.assertEqual((plan.kind, plan.reason), ("relayout", "disconnect"))
        self.assertEqual(plan.size, (1200, 750))
        final = response.handle_native_change(
            {"source": "kscreen.configChanged", "outputs": []})
        self.assertEqual((final.kind, final.reason), ("suspend", "no_display"))


if __name__ == "__main__":
    unittest.main()
