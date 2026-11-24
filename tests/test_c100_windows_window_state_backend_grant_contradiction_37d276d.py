"""Regression: a known backend's advertised features bind its grants.

Pure in-process policy contract; no Qt, compositor, X11 or Wayland is used.
A Negotiation record whose backend names a registered profile cannot grant a
feature that profile does not advertise: `allows()` and the controller must
not turn that contradiction into a false capability claim.
"""

import unittest

from canopy_features.windows.window_state_capabilities import (
    BackendProfile,
    Negotiation,
    WindowState,
    WindowStateAction,
    WindowStateController,
    WindowStateFeature,
    negotiate,
)

ALL = frozenset(WindowStateFeature)
MIN = WindowStateAction.MINIMIZE
MAX = WindowStateAction.MAXIMIZE
RES = WindowStateAction.RESTORE


class HostileBackendName(str):
    """A bounded label whose hash raises, used to prove no raw TypeError."""

    def __hash__(self):
        raise TypeError("hostile hash")


class BackendGrantContradictionTests(unittest.TestCase):
    def test_headless_cannot_grant_features_its_profile_lacks(self):
        record = Negotiation("headless", "SUPPORTED", ALL)
        for action in (MIN, MAX, RES):
            with self.subTest(action=action):
                self.assertFalse(record.allows(action))

    def test_wayland_cannot_grant_minimize_its_profile_lacks(self):
        record = Negotiation("wayland", "SUPPORTED", ALL)
        for action in (MIN, MAX, RES):
            with self.subTest(action=action):
                self.assertFalse(record.allows(action))

    def test_partial_record_cannot_grant_unadvertised_feature(self):
        record = Negotiation("wayland", "PARTIAL", ALL)
        self.assertFalse(record.allows(MIN))

    def test_controller_rejects_contradictory_backend_grant(self):
        record = Negotiation("headless", "SUPPORTED", ALL)
        controller = WindowStateController(record)
        result = controller.apply(MIN)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "FEATURE_NOT_GRANTED")
        self.assertIs(controller.state, WindowState.NORMAL)
        self.assertFalse(controller.allows(MIN))

    def test_negotiated_records_keep_advertised_features(self):
        x11 = negotiate("x11", ALL)
        for action in (MIN, MAX, RES):
            self.assertTrue(x11.allows(action))
        wayland = negotiate("wayland", ALL)
        self.assertFalse(wayland.allows(MIN))
        self.assertTrue(wayland.allows(MAX))
        headless = negotiate("headless", ALL)
        for action in (MIN, MAX, RES):
            self.assertFalse(headless.allows(action))
        custom = negotiate(
            BackendProfile("custom", frozenset({WindowStateFeature.MINIMIZE})),
            frozenset({WindowStateFeature.MINIMIZE}),
        )
        self.assertTrue(custom.allows(MIN))

    def test_hostile_bounded_backend_label_does_not_leak_raw_error(self):
        record = Negotiation(HostileBackendName("headless"), "SUPPORTED", ALL)
        self.assertFalse(record.allows(MIN))


if __name__ == "__main__":
    unittest.main()
