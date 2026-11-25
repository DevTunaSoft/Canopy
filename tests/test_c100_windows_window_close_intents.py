"""Offline unit tests for non-destructive window close request semantics.

These tests exercise an in-memory decision model only. They do not run Qt,
QML, a compositor, Linux Mint or any desktop session.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.windows.window_close_intents import (
    ACCEPTED, ALREADY_CLOSED, ALREADY_OPEN, CLOSED, CloseIntentModel,
    CloseRequestError, GUARDED, IntentResult, MAX_WINDOWS, REOPENED,
    STATUSES, UNKNOWN_WINDOW, OWNERSHIP_DENIED,
)

SOURCE = (Path(__file__).resolve().parents[1] / "canopy_features" /
          "windows" / "window_close_intents.py")


class WindowCloseIntentTests(unittest.TestCase):
    def setUp(self):
        self.model = CloseIntentModel()
        self.state = {
            "path": "/home/user/Documents",
            "search_query": "report",
            "entry_count": 12,
        }

    def register_files(self, **kwargs):
        self.model.register("files", "host.files", self.state, **kwargs)

    def test_close_parks_window_and_preserves_state_for_reopen(self):
        self.register_files()
        original = dict(self.model.snapshot("files", "host.files"))

        closed = self.model.request_close("files", "host.files")

        self.assertEqual((closed.status, closed.visible), (CLOSED, False))
        self.assertTrue(closed.accepted)
        self.assertEqual(dict(closed.state), original)
        self.assertEqual(dict(self.model.snapshot("files", "host.files")), original)
        self.assertEqual(self.model.window_count, 1)

        reopened = self.model.reopen("files", "host.files")

        self.assertEqual((reopened.status, reopened.visible), (REOPENED, True))
        self.assertEqual(dict(reopened.state), original)
        self.assertEqual(dict(self.model.snapshot("files", "host.files")), original)
        self.assertEqual(self.model.window_count, 1)

    def test_unknown_or_malformed_window_is_never_closed(self):
        self.register_files()
        for bad_id in ("missing", "BAD ID", "", None, 7, True):
            with self.subTest(window_id=bad_id):
                result = self.model.request_close(bad_id, "host.files")
                self.assertEqual(result.status, UNKNOWN_WINDOW)
                self.assertIsNone(result.visible)
                self.assertFalse(result.accepted)
                self.assertEqual(dict(result.state), {})
        self.assertEqual(self.model.window_count, 1)
        self.assertEqual(dict(self.model.snapshot("missing", "host.files")), {})
        self.assertEqual(self.model.request_close("missing", "host.files").status,
                         UNKNOWN_WINDOW)

    def test_disallowed_ownership_is_refused_without_state_disclosure(self):
        self.register_files()

        denied = self.model.request_close("files", "rogue.app")

        self.assertEqual(denied.status, OWNERSHIP_DENIED)
        self.assertIsNone(denied.visible)
        self.assertFalse(denied.accepted)
        self.assertEqual(dict(denied.state), {})
        self.assertEqual(dict(self.model.snapshot("files", "rogue.app")), {})
        self.assertFalse(self.model.set_guard("files", "rogue.app", True))
        self.assertFalse(self.model.update_state(
            "files", "rogue.app", path="/etc/passwd"))
        denied_reopen = self.model.reopen("files", "rogue.app")
        self.assertEqual(denied_reopen.status, OWNERSHIP_DENIED)
        self.assertIsNone(denied_reopen.visible)
        self.assertEqual(dict(denied_reopen.state), {})
        self.assertFalse(self.model.release("files", "rogue.app"))

        self.assertEqual(dict(self.model.snapshot("files", "host.files")),
                         self.state)
        self.assertEqual(self.model.request_close("files", "host.files").status,
                         CLOSED)
        for bad_owner in (None, 5, "Bad Owner", ""):
            with self.subTest(owner=bad_owner):
                self.assertEqual(
                    self.model.request_close("files", bad_owner).status,
                    UNKNOWN_WINDOW)

    def test_owner_guard_refuses_close_without_state_loss(self):
        self.register_files()
        self.assertTrue(self.model.set_guard("files", "host.files", True))

        guarded = self.model.request_close("files", "host.files")

        self.assertEqual((guarded.status, guarded.visible), (GUARDED, True))
        self.assertFalse(guarded.accepted)
        self.assertEqual(dict(guarded.state), self.state)
        self.assertEqual(dict(self.model.snapshot("files", "host.files")),
                         self.state)

        self.assertTrue(self.model.set_guard("files", "host.files", False))
        self.assertEqual(self.model.request_close("files", "host.files").status,
                         CLOSED)
        self.assertTrue(self.model.reopen("files", "host.files"))

    def test_repeated_close_and_reopen_are_idempotent(self):
        self.register_files()
        self.model.request_close("files", "host.files")

        again = self.model.request_close("files", "host.files")
        self.assertEqual((again.status, again.visible), (ALREADY_CLOSED, False))
        self.assertEqual(dict(again.state), self.state)

        self.model.reopen("files", "host.files")
        already = self.model.reopen("files", "host.files")
        self.assertEqual((already.status, already.visible), (ALREADY_OPEN, True))
        self.assertEqual(dict(already.state), self.state)
        self.assertEqual(self.model.window_count, 1)

    def test_state_updates_survive_park_and_reopen(self):
        self.register_files()
        self.model.request_close("files", "host.files")
        self.assertTrue(self.model.update_state(
            "files", "host.files", search_query="budget", entry_count=3))
        self.model.reopen("files", "host.files")

        expected = dict(self.state, search_query="budget", entry_count=3)
        self.assertEqual(dict(self.model.snapshot("files", "host.files")),
                         expected)
        self.assertEqual(dict(self.model.request_close(
            "files", "host.files").state), expected)

    def test_registry_is_bounded_and_rejects_duplicates(self):
        model = CloseIntentModel(max_windows=2)
        model.register("files", "host.files")
        model.register("trash", "host.files")
        with self.assertRaisesRegex(CloseRequestError, "duplicate"):
            model.register("files", "host.files")
        with self.assertRaisesRegex(CloseRequestError, "limit"):
            model.register("third", "host.files")
        self.assertEqual(model.window_count, 2)
        with self.assertRaises(CloseRequestError):
            CloseIntentModel(max_windows=MAX_WINDOWS + 1)

    def test_registration_validation_and_immutable_state_snapshot(self):
        for bad_id, bad_owner in (("Bad", "host.files"),
                                  ("files", "Bad Owner"),
                                  ("", "host.files"),
                                  ("files", "")):
            with self.subTest(window_id=bad_id, owner=bad_owner):
                with self.assertRaises(CloseRequestError):
                    self.model.register(bad_id, bad_owner)
        with self.assertRaises(CloseRequestError):
            self.model.register("bad-visible", "host.files", visible=1)
        with self.assertRaises(CloseRequestError):
            self.model.register("bad-state", "host.files", {"nested": {}})
        with self.assertRaises(CloseRequestError):
            self.model.register("bad-float", "host.files",
                                {"ratio": float("nan")})
        with self.assertRaises(CloseRequestError):
            self.model.register("bad-name", "host.files", {"Bad Name": 1})
        with self.assertRaises(CloseRequestError):
            self.model.register("too-long", "host.files",
                                {"title": "x" * 300})
        with self.assertRaises(CloseRequestError):
            self.model.register("too-many", "host.files",
                                {"f" + str(i): i for i in range(17)})
        self.assertEqual(self.model.window_count, 0)

        self.register_files()
        result = self.model.request_close("files", "host.files")
        with self.assertRaises(TypeError):
            result.state["path"] = "/etc"
        with self.assertRaises(TypeError):
            self.model.snapshot("files", "host.files")["path"] = "/etc"
        with self.assertRaises(CloseRequestError):
            self.model.update_state("files", "host.files", nested=[])
        self.assertEqual(dict(self.model.snapshot("files", "host.files")),
                         self.state)

    def test_release_is_owner_scoped_and_distinct_from_close(self):
        self.register_files()
        self.assertEqual(self.model.request_close("files", "host.files").status,
                         CLOSED)
        self.assertEqual(self.model.window_count, 1)
        self.assertFalse(self.model.release("files", "rogue.app"))
        self.assertEqual(self.model.window_count, 1)
        self.assertTrue(self.model.release("files", "host.files"))
        self.assertEqual(self.model.window_count, 0)
        self.assertEqual(self.model.request_close("files", "host.files").status,
                         UNKNOWN_WINDOW)

    def test_repeated_cycles_do_not_grow_records_or_state(self):
        self.register_files()
        for cycle in range(40):
            self.assertEqual(self.model.request_close(
                "files", "host.files").status, CLOSED)
            self.assertTrue(self.model.update_state(
                "files", "host.files", entry_count=cycle))
            self.assertEqual(self.model.reopen("files", "host.files").status,
                             REOPENED)
        self.assertEqual(self.model.window_count, 1)
        self.assertEqual(len(self.model.snapshot("files", "host.files")),
                         len(self.state))

    def test_status_vocabulary_and_frozen_result(self):
        self.assertTrue(ACCEPTED.issubset(STATUSES))
        self.assertEqual(len(STATUSES), 7)
        result = IntentResult("files", GUARDED, True)
        self.assertFalse(result.accepted)
        with self.assertRaises(FrozenInstanceError):
            result.status = UNKNOWN_WINDOW

    def test_no_polling_threads_services_or_privileged_actions(self):
        code = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("QTimer", "Thread(", "import socket", "subprocess",
                          "time.sleep", "asyncio", "while True", "importlib",
                          "os.system", "import PyQt", "from PySide"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
