"""Tests for the immutable shell-action decision composer.

Run: python -m unittest tests.test_c100_launcher_shell_action_decision -v
No Qt runtime, process launch, filesystem walk or network is involved.
"""
import unittest

from canopy_features.apps.file_manager_intent import LAUNCH_ACTION
from canopy_features.apps import files_intent_preview as files_mod
from canopy_features.dock import dock_action_preview as dock_mod
from canopy_features.dock.dock_action_preview import DockActionPreview
from canopy_features.apps.files_intent_preview import FilesIntentPreview
from canopy_features.launcher.app_search_casefold import EXACT, Match
from canopy_features.launcher.launcher_keyboard_navigation import NO_FOCUS
from canopy_features.launcher.launcher_search_view import (
    STATUS_EMPTY as SEARCH_EMPTY,
    STATUS_READY as SEARCH_READY,
    SearchView,
)
from canopy_features.launcher.shell_action_decision import (
    MAX_TARGET_CHARS,
    REASON_AMBIGUOUS,
    REASON_NO_ACTION,
    REASON_OK,
    REASON_SOURCE_DISAGREEMENT,
    REASON_SURFACE_NOT_ACTIONABLE,
    STATUS_DENIED,
    STATUS_IDLE,
    STATUS_READY,
    SURFACE_DOCK,
    SURFACE_FILES,
    SURFACE_LAUNCHER,
    ShellActionCompositionError,
    ShellActionDecision,
    compose_shell_action_decision,
)


def dock_ready():
    return DockActionPreview(
        dock_mod.APPROVED, dock_mod.REASON_OK, action="launch", target="Files",
        pinned_index=0, running_pids=0, intent_reason="installed",
        indicator_sequence=1, focus_was_on_target=False)


def dock_denied():
    return DockActionPreview(dock_mod.DENIED, dock_mod.REASON_NOT_PINNED)


def launcher_ready():
    return SearchView("fire", (Match("Firefox", EXACT, 0),),
                      0, "Firefox", SEARCH_READY)


def launcher_empty():
    return SearchView("", (), NO_FOCUS, None, SEARCH_EMPTY)


def files_ready():
    return FilesIntentPreview(
        files_mod.APPROVED, files_mod.REASON_OK, action=LAUNCH_ACTION,
        uri="file:///home/u/Docs", directory="/home/u/Docs",
        policy_reason="ok")


def files_denied():
    return FilesIntentPreview(
        files_mod.DENIED, files_mod.REASON_POLICY_DENIED,
        policy_reason="outside_home")


class ContractTests(unittest.TestCase):
    def test_constants_are_stable(self):
        self.assertEqual(STATUS_READY, "READY")
        self.assertEqual(STATUS_IDLE, "IDLE")
        self.assertEqual(STATUS_DENIED, "DENIED")
        self.assertEqual(SURFACE_DOCK, "dock")
        self.assertEqual(SURFACE_LAUNCHER, "launcher")
        self.assertEqual(SURFACE_FILES, "files")
        self.assertEqual(REASON_OK, "ok")
        self.assertEqual(REASON_NO_ACTION, "no_action")
        self.assertEqual(REASON_AMBIGUOUS, "ambiguous_surface")
        self.assertEqual(REASON_SURFACE_NOT_ACTIONABLE, "surface_not_actionable")
        self.assertEqual(REASON_SOURCE_DISAGREEMENT, "source_disagreement")
        self.assertIs(type(MAX_TARGET_CHARS), int)


class ArbitrationTests(unittest.TestCase):
    def test_dock_only_ready(self):
        decision = compose_shell_action_decision(
            dock_ready(), launcher_empty(), files_denied())
        self.assertEqual(decision, ShellActionDecision(
            STATUS_READY, REASON_OK, SURFACE_DOCK, "launch", "Files"))
        self.assertTrue(decision.ready)

    def test_launcher_only_ready(self):
        decision = compose_shell_action_decision(
            dock_denied(), launcher_ready(), files_denied())
        self.assertEqual(decision, ShellActionDecision(
            STATUS_READY, REASON_OK, SURFACE_LAUNCHER, "select", "Firefox"))

    def test_files_only_ready(self):
        decision = compose_shell_action_decision(
            dock_denied(), launcher_empty(), files_ready())
        self.assertEqual(decision, ShellActionDecision(
            STATUS_READY, REASON_OK, SURFACE_FILES,
            LAUNCH_ACTION, "file:///home/u/Docs"))

    def test_no_actionable_is_idle(self):
        decision = compose_shell_action_decision(
            dock_denied(), launcher_empty(), files_denied())
        self.assertEqual(decision, ShellActionDecision(
            STATUS_IDLE, REASON_NO_ACTION))
        self.assertFalse(decision.ready)

    def test_two_actionable_without_pin_is_ambiguous(self):
        decision = compose_shell_action_decision(
            dock_ready(), launcher_ready(), files_denied())
        self.assertEqual(decision, ShellActionDecision(
            STATUS_DENIED, REASON_AMBIGUOUS))
        self.assertIsNone(decision.target)

    def test_pin_selects_dock_among_two(self):
        decision = compose_shell_action_decision(
            dock_ready(), launcher_ready(), files_denied(),
            active_surface=SURFACE_DOCK)
        self.assertEqual(decision.surface, SURFACE_DOCK)
        self.assertEqual(decision.action, "launch")
        self.assertEqual(decision.target, "Files")

    def test_pin_selects_files_among_two(self):
        decision = compose_shell_action_decision(
            dock_ready(), launcher_empty(), files_ready(),
            active_surface=SURFACE_FILES)
        self.assertEqual(decision.surface, SURFACE_FILES)
        self.assertEqual(decision.target, "file:///home/u/Docs")

    def test_pin_to_non_actionable_surface_denied(self):
        decision = compose_shell_action_decision(
            dock_ready(), launcher_empty(), files_denied(),
            active_surface=SURFACE_FILES)
        self.assertEqual(decision, ShellActionDecision(
            STATUS_DENIED, REASON_SURFACE_NOT_ACTIONABLE))

    def test_idle_to_dict_has_no_payload(self):
        payload = compose_shell_action_decision(
            dock_denied(), launcher_empty(), files_denied()).to_dict()
        self.assertEqual(payload, {
            "status": STATUS_IDLE, "reason": REASON_NO_ACTION,
            "surface": None, "action": None, "target": None})

    def test_ready_to_dict(self):
        payload = compose_shell_action_decision(
            dock_denied(), launcher_ready(), files_denied()).to_dict()
        self.assertEqual(payload, {
            "status": STATUS_READY, "reason": REASON_OK,
            "surface": SURFACE_LAUNCHER, "action": "select",
            "target": "Firefox"})


class FailClosedTests(unittest.TestCase):
    def test_invalid_surface_value_raises(self):
        with self.assertRaises(ShellActionCompositionError):
            compose_shell_action_decision(
                dock_ready(), launcher_empty(), files_denied(),
                active_surface="tray")

    def test_invalid_surface_type_raises(self):
        with self.assertRaises(ShellActionCompositionError):
            compose_shell_action_decision(
                dock_ready(), launcher_empty(), files_denied(),
                active_surface=7)

    def test_wrong_dock_type_raises(self):
        with self.assertRaises(ShellActionCompositionError):
            compose_shell_action_decision(
                "not a preview", launcher_empty(), files_denied())

    def test_wrong_launcher_type_raises(self):
        with self.assertRaises(ShellActionCompositionError):
            compose_shell_action_decision(
                dock_ready(), (), files_denied())

    def test_wrong_files_type_raises(self):
        with self.assertRaises(ShellActionCompositionError):
            compose_shell_action_decision(
                dock_ready(), launcher_empty(), {})

    def test_inconsistent_dock_record_denied(self):
        bad = DockActionPreview(
            dock_mod.APPROVED, dock_mod.REASON_NOT_PINNED,
            action="launch", target="Files", pinned_index=0, running_pids=0)
        decision = compose_shell_action_decision(
            bad, launcher_empty(), files_denied())
        self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)
        self.assertIsNone(decision.target)

    def test_inconsistent_launcher_record_denied(self):
        bad = SearchView("fire", (Match("Firefox", EXACT, 0),),
                         0, "Thunderbird", SEARCH_READY)
        decision = compose_shell_action_decision(
            dock_denied(), bad, files_denied())
        self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)

    def test_inconsistent_files_record_denied(self):
        bad = FilesIntentPreview(
            files_mod.APPROVED, files_mod.REASON_OK,
            action=LAUNCH_ACTION, uri="http://example.invalid/payload",
            directory="/home/u/Docs")
        decision = compose_shell_action_decision(
            dock_denied(), launcher_empty(), bad)
        self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)
        self.assertIsNone(decision.target)

    def test_oversized_target_denied(self):
        bad = DockActionPreview(
            dock_mod.APPROVED, dock_mod.REASON_OK, action="launch",
            target="A" * (MAX_TARGET_CHARS + 1), pinned_index=0,
            running_pids=0)
        decision = compose_shell_action_decision(
            bad, launcher_empty(), files_denied())
        self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)

    def test_hostile_bounded_dock_target_denied(self):
        # Bounded length is not enough: format, separator, private-use,
        # noncharacter, C1 control and surrogate scalars are not printable
        # text and must never become an action-ready target.
        for unsafe in ("\u0085", "\u200b", "\u202e", "\u2028", "\ue000",
                       "\ufdd0", "\ud800"):
            with self.subTest(unsafe=repr(unsafe)):
                bad = DockActionPreview(
                    dock_mod.APPROVED, dock_mod.REASON_OK, action="launch",
                    target="Files" + unsafe, pinned_index=0, running_pids=0)
                decision = compose_shell_action_decision(
                    bad, launcher_empty(), files_denied())
                self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)
                self.assertEqual(decision.status, STATUS_DENIED)
                self.assertFalse(decision.ready)
                self.assertIsNone(decision.surface)
                self.assertIsNone(decision.action)
                self.assertIsNone(decision.target)

    def test_hostile_bounded_files_uri_denied(self):
        bad = FilesIntentPreview(
            files_mod.APPROVED, files_mod.REASON_OK, action=LAUNCH_ACTION,
            uri="file:///home/u/Docs\u202e.exe", directory="/home/u/Docs")
        decision = compose_shell_action_decision(
            dock_denied(), launcher_empty(), bad)
        self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)
        self.assertFalse(decision.ready)
        self.assertIsNone(decision.target)

    def test_hostile_bounded_launcher_name_denied(self):
        name = "Firefox\u200b"
        bad = SearchView("fire", (Match(name, EXACT, 0),), 0, name, SEARCH_READY)
        decision = compose_shell_action_decision(
            dock_denied(), bad, files_denied())
        self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)
        self.assertFalse(decision.ready)
        self.assertIsNone(decision.target)

    def test_unhashable_dock_action_denied(self):
        # An approved record whose action is an unhashable container is a
        # source disagreement: it must deny with the module's domain reason
        # and carry no payload, never leak a raw TypeError from set membership.
        for action in (["launch"], {"launch": 1}):
            with self.subTest(action=repr(action)):
                bad = DockActionPreview(
                    dock_mod.APPROVED, dock_mod.REASON_OK, action=action,
                    target="Files", pinned_index=0, running_pids=0)
                decision = compose_shell_action_decision(
                    bad, launcher_empty(), files_denied())
                self.assertEqual(decision.status, STATUS_DENIED)
                self.assertEqual(decision.reason, REASON_SOURCE_DISAGREEMENT)
                self.assertFalse(decision.ready)
                self.assertIsNone(decision.surface)
                self.assertIsNone(decision.action)
                self.assertIsNone(decision.target)

    def test_printable_unicode_target_still_ready(self):
        bad = DockActionPreview(
            dock_mod.APPROVED, dock_mod.REASON_OK, action="launch",
            target="Caf\u00e9", pinned_index=0, running_pids=0)
        decision = compose_shell_action_decision(
            bad, launcher_empty(), files_denied())
        self.assertEqual(decision.status, STATUS_READY)
        self.assertEqual(decision.target, "Caf\u00e9")

    def test_inputs_are_not_mutated(self):
        dock, search, files = dock_ready(), launcher_ready(), files_ready()
        before = (dock, search, files)
        compose_shell_action_decision(
            dock, search, files, active_surface=SURFACE_LAUNCHER)
        self.assertEqual((dock, search, files), before)


if __name__ == "__main__":
    unittest.main()
