"""Residual audit: a parked window must not report a close veto as "left open".

A window can be parked (``visible=False``) and still carry an owner guard,
either by registering it that way or by guarding it after a close.  The guard
flag and the visibility flag are individually legal but jointly determine the
close-state claim: once the window is parked there is no close left to veto.
On the unfixed model, ``request_close`` checks the guard first and returns
``GUARDED`` with ``visible=False`` and the note "owner guard active; window
left open" -- a contradictory close-state claim that a host could read as an
open window.  The status must be derived from the durable visibility flag.

This is pure in-memory state-machine testing: no Qt, QML, compositor, session,
files, processes, sockets or visual changes.
"""
import unittest

from canopy_features.windows.window_close_intents import (
    ALREADY_CLOSED,
    CLOSED,
    CloseIntentModel,
    GUARDED,
    REOPENED,
)


class CloseStateFlagContradictionTests(unittest.TestCase):
    def _parked_then_guarded(self):
        model = CloseIntentModel()
        model.register("files", "host.files", {"page": "home"},
                       visible=True)
        self.assertEqual(model.request_close("files", "host.files").status,
                         CLOSED)
        self.assertTrue(model.set_guard("files", "host.files", True))
        return model

    def test_close_on_parked_then_guarded_window_is_already_closed(self):
        model = self._parked_then_guarded()

        result = model.request_close("files", "host.files")

        self.assertEqual(result.status, ALREADY_CLOSED)
        self.assertIs(result.visible, False)
        self.assertTrue(result.accepted)
        self.assertNotIn("left open", result.note)
        self.assertEqual(dict(result.state), {"page": "home"})
        self.assertEqual(dict(model.snapshot("files", "host.files")),
                         {"page": "home"})

    def test_registered_parked_and_guarded_window_is_already_closed(self):
        model = CloseIntentModel()
        model.register("files", "host.files", {"page": "home"},
                       visible=False, guarded=True)

        result = model.request_close("files", "host.files")

        self.assertEqual(result.status, ALREADY_CLOSED)
        self.assertIs(result.visible, False)
        self.assertTrue(result.accepted)
        self.assertNotIn("left open", result.note)
        self.assertEqual(model.window_count, 1)

    def test_guard_still_vetoes_close_of_a_visible_window(self):
        model = CloseIntentModel()
        model.register("files", "host.files", {"page": "home"},
                       visible=True, guarded=True)

        guarded = model.request_close("files", "host.files")

        self.assertEqual(guarded.status, GUARDED)
        self.assertIs(guarded.visible, True)
        self.assertFalse(guarded.accepted)
        self.assertIn("left open", guarded.note)
        self.assertEqual(model.window_count, 1)

    def test_guard_lifecycle_across_park_and_reopen_stays_consistent(self):
        model = self._parked_then_guarded()
        self.assertEqual(model.request_close("files", "host.files").status,
                         ALREADY_CLOSED)
        self.assertEqual(model.reopen("files", "host.files").status, REOPENED)
        self.assertEqual(model.request_close("files", "host.files").status,
                         GUARDED)
        self.assertTrue(model.set_guard("files", "host.files", False))
        self.assertEqual(model.request_close("files", "host.files").status,
                         CLOSED)


if __name__ == "__main__":
    unittest.main()
