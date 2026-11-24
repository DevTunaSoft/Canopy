"""Tests for the pure, no-echo desktop-action launch preview.

Run: python -m unittest tests.test_c100_apps_desktop_action_launch_preview -v
No process launch, shell, filesystem walk or desktop is involved.
"""
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from canopy_features.apps import desktop_action_launch_preview as preview_mod
from canopy_features.apps.desktop_action_launch_preview import (
    FIXED_CLAIMS,
    REASON_INVALID_ACTIONS,
    REASON_INVALID_ARGV,
    REASON_INVALID_INPUT,
    REASON_OK,
    REASON_SOURCE_DISAGREEMENT,
    REASON_UNAPPROVED_ACTION,
    REASON_UNSAFE_EXEC,
    STATUS_DENIED,
    STATUS_READY,
    DesktopActionLaunchPreview,
    compose_desktop_action_launch_preview,
)
from canopy_features.apps.desktop_actions import (
    ActionProblem,
    DesktopAction,
    DesktopActionScan,
)

ENTRY = """[Desktop Entry]
Type=Application
Name=Example
Actions=NewWindow;SecretAction;

[Desktop Action NewWindow]
Name=New Window
Exec=/usr/bin/example --new-window
Icon=example

[Desktop Action SecretAction]
Name=SECRETDISPLAY
Exec=/usr/bin/example --secret SECRETEXECVALUE
Icon=secret-icon
"""
ALLOWED_ACTIONS = ("NewWindow", "SecretAction")
EXECUTABLE = "/usr/bin/example"


def compose(text=ENTRY, **overrides):
    options = dict(
        allowed_action_ids=ALLOWED_ACTIONS,
        executable=EXECUTABLE,
        allowed_executables=(EXECUTABLE,),
        arguments=("--new-window",),
    )
    options.update(overrides)
    return compose_desktop_action_launch_preview(text, **options)


class ApprovedTests(unittest.TestCase):
    def test_constants_are_fixed_negative_claims(self):
        self.assertEqual(STATUS_READY, "READY")
        self.assertEqual(STATUS_DENIED, "DENIED")
        self.assertEqual(REASON_OK, "ok")
        self.assertIsInstance(FIXED_CLAIMS, tuple)
        self.assertTrue(FIXED_CLAIMS)
        self.assertTrue(all(type(c) is str for c in FIXED_CLAIMS))
        for claim in ("no_process_launched", "no_value_echo",
                      "no_shell_metacharacters", "no_field_codes",
                      "no_unapproved_action", "no_desktop_claim"):
            with self.subTest(claim=claim):
                self.assertIn(claim, FIXED_CLAIMS)

    def test_approved_counts_only(self):
        result = compose()
        self.assertEqual(result, DesktopActionLaunchPreview(
            STATUS_READY, REASON_OK, declared_count=2, action_count=2,
            argv_length=2, claims=FIXED_CLAIMS))
        self.assertTrue(result.ready)

    def test_no_action_or_exec_or_argv_values_are_echoed(self):
        payload = repr(compose().to_dict())
        for secret in ("SECRETDISPLAY", "SECRETEXECVALUE", "secret-icon",
                       "SecretAction", "NewWindow", EXECUTABLE, "--new-window"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, payload)

    def test_to_dict_shape(self):
        self.assertEqual(set(compose().to_dict()), {
            "status", "reason", "declared_count", "action_count",
            "argv_length", "claims"})

    def test_record_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            compose().action_count = 99

    def test_no_process_spawner_import(self):
        with open(preview_mod.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("Popen", source)
        self.assertNotIn("os.system", source)

    def test_entry_without_actions_is_approved_with_zero_counts(self):
        result = compose("[Desktop Entry]\nType=Application\nName=Example\n")
        self.assertEqual(result.declared_count, 0)
        self.assertEqual(result.action_count, 0)
        self.assertEqual(result.claims, FIXED_CLAIMS)


class DenialTests(unittest.TestCase):
    def assert_terse_denial(self, result, reason):
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, reason)
        self.assertFalse(result.ready)
        self.assertEqual(result.declared_count, 0)
        self.assertEqual(result.action_count, 0)
        self.assertEqual(result.argv_length, 0)
        self.assertEqual(result.claims, ())

    def test_invalid_actions_are_denied_without_problem_echo(self):
        text = ENTRY.replace("Actions=NewWindow;SecretAction;",
                             "Actions=NewWindow;Missing;")
        result = compose(text)
        self.assert_terse_denial(result, REASON_INVALID_ACTIONS)
        self.assertNotIn("Missing", repr(result.to_dict()))

    def test_unapproved_action_is_denied_without_echo(self):
        result = compose(allowed_action_ids=("NewWindow",))
        self.assert_terse_denial(result, REASON_UNAPPROVED_ACTION)
        self.assertNotIn("SecretAction", repr(result.to_dict()))

    def test_field_code_exec_is_denied(self):
        text = ENTRY.replace("--secret SECRETEXECVALUE", "--secret %U")
        self.assert_terse_denial(compose(text), REASON_UNSAFE_EXEC)

    def test_shell_metacharacter_exec_is_denied(self):
        text = ENTRY.replace("--secret SECRETEXECVALUE", "--secret;echo")
        self.assert_terse_denial(compose(text), REASON_UNSAFE_EXEC)

    def test_unapproved_executable_is_denied(self):
        self.assert_terse_denial(
            compose(allowed_executables=("/usr/bin/other",)),
            REASON_INVALID_ARGV)

    def test_wrong_text_type_is_denied(self):
        self.assert_terse_denial(compose(7), REASON_INVALID_INPUT)

    def test_source_disagreement_is_fault_injected(self):
        with patch.object(preview_mod, "build_launch_argv",
                          return_value=("SECRET-ARGV-TOKEN",)):
            result = compose()
        self.assert_terse_denial(result, REASON_SOURCE_DISAGREEMENT)
        self.assertNotIn("SECRET-ARGV-TOKEN", repr(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
