"""Offline unit tests for the Wayland portal capability descriptor.

Run on any host, including Windows. No D-Bus, Mint guest, Qt binary or
window server is required, used or pretended.
"""
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canopy_features.windows.wayland_portal_capabilities import (  # noqa: E402
    PORTAL_INTERFACES,
    SCHEMA_VERSION,
    WINDOW_ENUMERATION,
    PortalCapabilityError,
    describe,
)

BOTH = ("remote_desktop", "screen_cast")
GRANT_BOTH = {"remote_desktop": "granted", "screen_cast": "granted"}


def _by_id(report):
    return {cap.capability: cap for cap in report.capabilities}


class WaylandPortalCapabilityTests(unittest.TestCase):
    def test_granted_portals_are_available_and_usable(self):
        report = describe("wayland", BOTH, GRANT_BOTH)
        self.assertEqual(report.schema_version, SCHEMA_VERSION)
        self.assertTrue(report.wayland)
        self.assertEqual(report.session_type, "wayland")
        self.assertEqual(report.window_enumeration, WINDOW_ENUMERATION)
        self.assertEqual(report.window_enumeration, "NOT_PERFORMED")
        by_id = _by_id(report)
        self.assertEqual(set(by_id), set(BOTH))
        for cap in by_id.values():
            self.assertEqual(cap.status, "available")
            self.assertEqual(cap.permission, "granted")
            self.assertTrue(cap.present)
            self.assertTrue(cap.usable)
            self.assertEqual(cap.interface, PORTAL_INTERFACES[cap.capability])
        self.assertEqual(report.usable, frozenset(BOTH))
        self.assertTrue(report.any_usable)
        self.assertEqual((report.denied, report.missing,
                          report.unknown_permission), (frozenset(),) * 3)

    def test_denied_permission_is_reported_and_not_usable(self):
        permissions = dict(GRANT_BOTH, screen_cast="denied")
        report = describe("wayland", BOTH, permissions)
        cast = _by_id(report)["screen_cast"]
        self.assertEqual(cast.status, "permission-denied")
        self.assertEqual(cast.permission, "denied")
        self.assertTrue(cast.present)
        self.assertFalse(cast.usable)
        self.assertEqual(report.denied, frozenset({"screen_cast"}))
        self.assertEqual(report.usable, frozenset({"remote_desktop"}))
        self.assertEqual(report.missing, frozenset())

    def test_missing_portal_is_reported_and_not_usable(self):
        report = describe("wayland", ("remote_desktop",), GRANT_BOTH)
        cast = _by_id(report)["screen_cast"]
        self.assertEqual(cast.status, "portal-missing")
        self.assertEqual(cast.permission, "absent")
        self.assertFalse(cast.present)
        self.assertFalse(cast.usable)
        self.assertEqual(report.missing, frozenset({"screen_cast"}))
        self.assertEqual(report.usable, frozenset({"remote_desktop"}))
        self.assertEqual(report.denied, frozenset())

    def test_all_portals_missing(self):
        report = describe("wayland", (), {})
        self.assertEqual(report.missing, frozenset(BOTH))
        self.assertEqual(report.usable, frozenset())
        self.assertFalse(report.any_usable)
        for cap in report.capabilities:
            self.assertEqual(cap.status, "portal-missing")
            self.assertEqual(cap.permission, "absent")

    def test_unknown_permission_fails_closed(self):
        report = describe("wayland", ("screen_cast",), {})
        cast = _by_id(report)["screen_cast"]
        self.assertEqual(cast.status, "permission-unknown")
        self.assertEqual(cast.permission, "unknown")
        self.assertTrue(cast.present)
        self.assertFalse(cast.usable)
        self.assertEqual(report.unknown_permission, frozenset({"screen_cast"}))
        self.assertEqual(report.usable, frozenset())

    def test_denied_permission_on_absent_portal_stays_missing(self):
        report = describe("wayland", (), {"screen_cast": "denied"})
        cast = _by_id(report)["screen_cast"]
        self.assertEqual(cast.status, "portal-missing")
        self.assertEqual(cast.permission, "absent")
        self.assertEqual(report.denied, frozenset())

    def test_non_wayland_session_exposes_no_portal_capability(self):
        report = describe("x11", BOTH, GRANT_BOTH)
        self.assertFalse(report.wayland)
        self.assertEqual(report.session_type, "x11")
        self.assertEqual(report.usable, frozenset())
        self.assertFalse(report.any_usable)
        for cap in report.capabilities:
            self.assertEqual(cap.status, "not-wayland")
            self.assertFalse(cap.usable)

    def test_unknown_session_value_is_normalized_and_not_echoed(self):
        token = "wayland-private-token-77"
        report = describe(token, BOTH, GRANT_BOTH)
        self.assertEqual(report.session_type, "unknown")
        self.assertFalse(report.wayland)
        self.assertEqual(report.usable, frozenset())
        self.assertNotIn(token, repr(report))
        self.assertNotIn(token, "".join(cap.status for cap in report.capabilities))

    def test_unknown_portal_id_rejected(self):
        with self.assertRaises(PortalCapabilityError):
            describe("wayland", ("root",), {})
        with self.assertRaises(PortalCapabilityError):
            describe("wayland", BOTH, {"root": "granted"})

    def test_invalid_permission_state_rejected(self):
        with self.assertRaises(PortalCapabilityError):
            describe("wayland", BOTH, {"screen_cast": "root"})

    def test_malformed_observations_rejected(self):
        for present, grants in (
            ("screen_cast", {}),
            (BOTH + ("extra",), {}),
            (BOTH, ["granted"]),
            (BOTH, {"screen_cast": "granted", "remote_desktop": "granted",
                    "extra": "granted"}),
        ):
            with self.subTest(present=present, grants=grants):
                with self.assertRaises(PortalCapabilityError):
                    describe("wayland", present, grants)

    def test_report_is_immutable(self):
        report = describe("wayland", BOTH, GRANT_BOTH)
        with self.assertRaises(FrozenInstanceError):
            report.wayland = False
        cap = report.capabilities[0]
        with self.assertRaises(FrozenInstanceError):
            cap.status = "available"
        with self.assertRaises(AttributeError):
            report.usable.add("root")

    def test_capability_allowlist_is_fixed_and_window_enumeration_absent(self):
        self.assertEqual(set(PORTAL_INTERFACES), set(BOTH))
        self.assertEqual(
            set(PORTAL_INTERFACES.values()),
            {"org.freedesktop.portal.RemoteDesktop",
             "org.freedesktop.portal.ScreenCast"},
        )
        self.assertNotIn("window", PORTAL_INTERFACES)
        report = describe("wayland", (), {})
        self.assertEqual(len(report.capabilities), 2)

    def test_source_has_no_polling_services_or_privileged_calls(self):
        source = (ROOT / "canopy_features" / "windows"
                  / "wayland_portal_capabilities.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "socket", "Gio", "while True",
                          "sleep", "os.environ", "import os", "threading",
                          "query_windows", "enumerate("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIn("NOT_PERFORMED", source)


if __name__ == "__main__":
    unittest.main()
