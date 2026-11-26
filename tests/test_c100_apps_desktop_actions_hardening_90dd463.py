"""PE-006: bounded, fail-closed desktop-action entry parsing.

QA-004 finding F02: action text was split into lines before any byte cap, so a
finite oversized entry could be amplified into many line objects before a
decision. ``str.splitlines()`` also consumes C0 and Unicode separators, which
can rewrite a hostile group heading into a clean-looking action. These tests
require a refusal before the split, bounded temporary allocations, and a
no-echo denial through the shell-free launch preview.

Pure in-memory tests: no process launch, shell, filesystem walk or desktop.
"""
import inspect
import tracemalloc
import unittest

from canopy_features.apps import desktop_actions as actions_mod
from canopy_features.apps import desktop_action_launch_preview as preview_mod
from canopy_features.apps.desktop_action_launch_preview import (
    REASON_INVALID_INPUT,
    REASON_UNSAFE_EXEC,
    STATUS_DENIED,
    compose_desktop_action_launch_preview,
)

# QA-004 remediation names 64 KiB, matching desktop_entry_parser.DEFAULT_MAX_BYTES.
_TEXT_LIMIT = 64 * 1024
_PEAK_LIMIT = 256 * 1024
_EXECUTABLE = "/usr/bin/demo"


def _good_entry():
    return (
        "[Desktop Entry]\nType=Application\nName=Demo\nActions=open;\n"
        "[Desktop Action open]\nName=Open\nExec=%s --open\n" % _EXECUTABLE
    )


def _preview(text):
    return compose_desktop_action_launch_preview(
        text,
        allowed_action_ids=("open",),
        executable=_EXECUTABLE,
        allowed_executables=(_EXECUTABLE,),
        arguments=("--open",),
    )


class ByteLimitTests(unittest.TestCase):
    def test_max_text_bytes_constant_is_declared(self):
        self.assertEqual(getattr(actions_mod, "MAX_TEXT_BYTES", None), _TEXT_LIMIT)

    def test_oversized_entry_is_refused_before_line_split(self):
        # Finite input only: no unbounded generator in a RED test.
        payload = "# " + ("x" * (_TEXT_LIMIT + 1))
        with self.assertRaises(ValueError):
            actions_mod.parse_desktop_actions(payload)

    def test_many_line_entry_allocation_is_bounded(self):
        # ~64 KiB of 1-character lines: base splitlines() builds tens of
        # thousands of str objects (QA-004 measured ~13x amplification).
        payload = "# " + ("x\n" * (_TEXT_LIMIT // 2))
        tracemalloc.start()
        try:
            try:
                actions_mod.parse_desktop_actions(payload)
            except ValueError:
                pass
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, _PEAK_LIMIT, "oversized text amplified to %d bytes" % peak)

    def test_multibyte_text_over_byte_limit_is_refused(self):
        # Fewer characters than the byte cap, but more UTF-8 bytes.
        payload = "# " + ("é" * (_TEXT_LIMIT // 2 + 1))
        self.assertLess(len(payload), _TEXT_LIMIT)
        with self.assertRaises(ValueError):
            actions_mod.parse_desktop_actions(payload)

    def test_exact_byte_limit_entry_still_parses(self):
        base = _good_entry()
        padding = _TEXT_LIMIT - len(base.encode("utf-8"))
        self.assertGreater(padding, 2)
        text = base + "# " + ("p" * (padding - 2))
        self.assertEqual(len(text.encode("utf-8")), _TEXT_LIMIT)
        scan = actions_mod.parse_desktop_actions(text)
        self.assertTrue(scan.ok, scan.problems)
        self.assertEqual(scan.declared_ids, ("open",))

    def test_lone_surrogate_is_refused_with_domain_error(self):
        payload = _good_entry() + "\n# \ud800"
        with self.assertRaises(ValueError):
            actions_mod.parse_desktop_actions(payload)


class MalformedLineTests(unittest.TestCase):
    def test_hidden_line_separator_cannot_manufacture_action_group(self):
        for separator in ("\x1c", "\u2028", "\u0085"):
            with self.subTest(separator=repr(separator)):
                payload = (
                    "[Desktop Entry]\nActions=open;\n"
                    "[Desktop Action open]" + separator + "Exec=/bin/sh\n"
                )
                with self.assertRaises(ValueError):
                    actions_mod.parse_desktop_actions(payload)

    def test_crlf_entry_still_parses(self):
        text = _good_entry().replace("\n", "\r\n")
        scan = actions_mod.parse_desktop_actions(text)
        self.assertTrue(scan.ok, scan.problems)
        self.assertEqual(scan.actions[0].exec_line, "%s --open" % _EXECUTABLE)


class PreviewBoundaryTests(unittest.TestCase):
    def test_oversized_text_is_denied_without_echo(self):
        payload = _good_entry() + "# " + ("HOSTILE_PADDING" * _TEXT_LIMIT)
        result = _preview(payload)
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, REASON_INVALID_INPUT)
        self.assertEqual(result.claims, ())
        self.assertNotIn("HOSTILE_PADDING", repr(result.to_dict()))

    def test_shell_substitution_exec_is_denied_without_interpolation(self):
        for suffix in ("$(touch /tmp/hostile)", "`touch /tmp/hostile`",
                       "| tee /tmp/hostile"):
            with self.subTest(suffix=suffix):
                text = _good_entry().replace(
                    "Exec=%s --open" % _EXECUTABLE,
                    "Exec=%s %s" % (_EXECUTABLE, suffix))
                result = _preview(text)
                self.assertEqual(result.status, STATUS_DENIED)
                self.assertEqual(result.reason, REASON_UNSAFE_EXEC)
                self.assertNotIn(suffix, repr(result.to_dict()))

    def test_no_shell_interpolation_source_contract(self):
        for module in (actions_mod, preview_mod):
            with self.subTest(module=module.__name__):
                source = inspect.getsource(module)
                for forbidden in ("subprocess", "Popen", "os.system", "shell=True"):
                    self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
