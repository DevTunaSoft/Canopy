"""Offline tests for the Wayland portal capability descriptor.

Injected data only. No D-Bus, compositor, portal service, window list, real
Mint session or compiled Qt binary is touched by these tests.
"""
import inspect
import json
from pathlib import Path
import unittest

from canopy_features.windows.wayland_portal_capabilities import (
    PORTAL_CAPABILITIES,
    PORTAL_INTERFACES,
    STATUS_AVAILABLE,
    STATUS_NOT_APPLICABLE,
    STATUS_PERMISSION_DENIED,
    STATUS_PORTAL_MISSING,
    WINDOW_ENUMERATION,
    describe,
    describe_from_preflight,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "canopy_features" / "windows" / "wayland_portal_capabilities.py"

ALL_INTERFACES = tuple(PORTAL_INTERFACES.values())
ALL_GRANTS = {name: True for name in PORTAL_CAPABILITIES}


class WaylandPortalCapabilityTests(unittest.TestCase):
    def report(self, **kwargs):
        return describe(
            kwargs.get("session_type", "wayland"),
            kwargs.get("wayland_display_present", True),
            kwargs.get("available_interfaces", ALL_INTERFACES),
            kwargs.get("permissions", ALL_GRANTS),
            kwargs.get("requested", None),
        )

    @staticmethod
    def by_name(report):
        return {cap.name: cap for cap in report.capabilities}

    # Present and permitted portals.
    def test_all_portals_present_and_granted_are_available(self):
        report = self.report()
        self.assertEqual(len(report.capabilities), len(PORTAL_CAPABILITIES))
        self.assertTrue(all(c.status == STATUS_AVAILABLE for c in report.capabilities))
        self.assertEqual(report.granted, PORTAL_CAPABILITIES)
        self.assertTrue(report.probe_only)
        self.assertTrue(all(c.available for c in report.capabilities))

    def test_report_is_json_serializable_and_bounded(self):
        data = self.report().to_dict()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["window_enumeration"], WINDOW_ENUMERATION)
        self.assertEqual(len(data["capabilities"]), len(PORTAL_CAPABILITIES))
        json.dumps(data)

    # Missing portals: never claim a portal that is not present.
    def test_missing_portal_is_reported_not_granted(self):
        present = tuple(i for i in ALL_INTERFACES
                        if i != PORTAL_INTERFACES["screen-cast"])
        screen = self.by_name(self.report(available_interfaces=present))["screen-cast"]
        self.assertEqual(screen.status, STATUS_PORTAL_MISSING)
        self.assertFalse(screen.portal_present)
        self.assertFalse(screen.permitted)
        self.assertFalse(screen.available)

    def test_no_portals_present_grants_nothing(self):
        report = self.report(available_interfaces=())
        self.assertTrue(all(c.status == STATUS_PORTAL_MISSING for c in report.capabilities))
        self.assertEqual(report.granted, frozenset())

    def test_unknown_interface_names_are_ignored(self):
        report = self.report(available_interfaces=("org.fake.Portal", "", None, 123))
        self.assertTrue(all(c.status == STATUS_PORTAL_MISSING for c in report.capabilities))

    # Denied permissions: never mark a denied capability available.
    def test_denied_permission_is_never_available(self):
        permissions = dict(ALL_GRANTS)
        permissions["screen-cast"] = False
        screen = self.by_name(self.report(permissions=permissions))["screen-cast"]
        self.assertEqual(screen.status, STATUS_PERMISSION_DENIED)
        self.assertTrue(screen.portal_present)
        self.assertFalse(screen.permitted)
        self.assertFalse(screen.available)
        self.assertNotIn("screen-cast", self.report(permissions=permissions).granted)

    def test_string_denied_is_honored(self):
        permissions = dict(ALL_GRANTS)
        permissions["remote-desktop"] = "denied"
        remote = self.by_name(self.report(permissions=permissions))["remote-desktop"]
        self.assertEqual(remote.status, STATUS_PERMISSION_DENIED)

    def test_missing_permission_entry_denies_by_default(self):
        report = self.report(permissions={})
        self.assertTrue(all(c.status == STATUS_PERMISSION_DENIED for c in report.capabilities))
        self.assertEqual(report.granted, frozenset())

    def test_truthy_non_grant_values_fail_closed(self):
        for value in (1, "yes", "TRUE ", None, [], {}, object()):
            with self.subTest(value=repr(value)):
                permissions = dict(ALL_GRANTS)
                permissions["settings"] = value
                cap = self.by_name(self.report(permissions=permissions))["settings"]
                self.assertEqual(cap.status, STATUS_PERMISSION_DENIED)

    def test_explicit_grant_forms(self):
        for value in (True, "granted", "GRANTED", "allow"):
            with self.subTest(value=repr(value)):
                permissions = dict(ALL_GRANTS)
                permissions["settings"] = value
                cap = self.by_name(self.report(permissions=permissions))["settings"]
                self.assertEqual(cap.status, STATUS_AVAILABLE)

    # Session gating and graceful fallback.
    def test_non_wayland_sessions_claim_no_portals(self):
        for session in ("x11", "X11", "tty", "unspecified", ""):
            with self.subTest(session=session):
                report = self.report(session_type=session)
                self.assertTrue(all(c.status == STATUS_NOT_APPLICABLE
                                    for c in report.capabilities))
                self.assertEqual(report.granted, frozenset())
                self.assertEqual(report.window_enumeration, WINDOW_ENUMERATION)

    def test_wayland_without_display_falls_back_gracefully(self):
        report = self.report(wayland_display_present=False)
        self.assertTrue(all(c.status == STATUS_NOT_APPLICABLE
                            for c in report.capabilities))
        self.assertFalse(report.wayland_display_present)
        self.assertEqual(report.session_type, "wayland")

    def test_session_type_is_normalized(self):
        self.assertEqual(self.report(session_type="Wayland").session_type, "wayland")
        self.assertEqual(self.report(session_type="unknown").session_type,
                         "other-or-unknown")

    # The core constraint: no unauthorized window enumeration.
    def test_window_enumeration_never_performed(self):
        self.assertEqual(WINDOW_ENUMERATION, "NOT_PERFORMED")
        self.assertEqual(self.report().window_enumeration, "NOT_PERFORMED")

    def test_api_has_no_window_listing_surface(self):
        names = set(inspect.signature(describe).parameters)
        self.assertFalse(any("window" in name for name in names))
        for forbidden in ("enumerate_windows", "list_windows", "query_windows"):
            self.assertNotIn(forbidden, names)

    def test_source_has_no_polling_background_or_privileged_calls(self):
        source = MODULE.read_text(encoding="utf-8")
        for forbidden in ("import subprocess", "import threading", "import time",
                          "while True", "Popen", "os.system", "enumerate_windows"):
            self.assertNotIn(forbidden, source)

    # Bounded inputs and validation.
    def test_unknown_requested_capability_rejected(self):
        with self.assertRaises(ValueError):
            self.report(requested=["screen-cast", "arbitrary-power"])

    def test_requested_subset_and_duplicates_are_bounded(self):
        report = self.report(requested=["settings", "open-uri", "settings"])
        self.assertEqual([c.name for c in report.capabilities], ["open-uri", "settings"])

    def test_invalid_inputs_raise_type_error(self):
        with self.assertRaises(TypeError):
            describe(None, True, (), {})
        with self.assertRaises(TypeError):
            describe("wayland", "yes", (), {})
        with self.assertRaises(TypeError):
            describe("wayland", True, "org.freedesktop.portal.Settings", {})
        with self.assertRaises(TypeError):
            describe("wayland", True, (), None)

    def test_report_is_immutable(self):
        report = self.report()
        with self.assertRaises(Exception):
            report.capabilities = ()

    # Reuse of the existing read-only preflight capability.
    def test_from_preflight_reuses_normalized_session_facts(self):
        preflight = {"session_type": "wayland", "graphical_display_present": True,
                     "mint_guest_acceptance": "NOT_RUN"}
        report = describe_from_preflight(preflight, ALL_INTERFACES, ALL_GRANTS)
        self.assertEqual(report.session_type, "wayland")
        self.assertEqual(report.granted, PORTAL_CAPABILITIES)
        self.assertTrue(report.probe_only)

    def test_from_preflight_x11_claims_no_portals(self):
        preflight = {"session_type": "x11", "graphical_display_present": True}
        report = describe_from_preflight(preflight, ALL_INTERFACES, ALL_GRANTS)
        self.assertEqual(report.granted, frozenset())

    def test_from_preflight_missing_fields_fail_closed(self):
        report = describe_from_preflight({}, (), {})
        self.assertEqual(report.session_type, "other-or-unknown")
        self.assertFalse(report.wayland_display_present)
        self.assertEqual(report.granted, frozenset())

    def test_from_preflight_rejects_non_mapping(self):
        with self.assertRaises(TypeError):
            describe_from_preflight(None, (), {})


if __name__ == "__main__":
    unittest.main()
