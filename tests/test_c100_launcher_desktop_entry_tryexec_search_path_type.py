"""Regression tests for controlled search_path typing in TryExec probing.

Run: python -m unittest tests.test_c100_launcher_desktop_entry_tryexec_search_path_type -v
No process launch, shell or real desktop is involved.
"""
import unittest

from canopy_features.launcher.desktop_entry_tryexec import (
    is_tryexec_available,
    tryexec_available_for_entry,
)

WRONG_PATHS = (
    ["/usr/bin", "/bin"],
    ("/usr/bin", "/bin"),
    {"PATH": "/usr/bin"},
    7,
    True,
    1.5,
    b"/usr/bin:/bin",
)


class SearchPathTypeTests(unittest.TestCase):
    """Wrong search_path types must be rejected by this module, not leaked."""

    def assert_controlled_type_error(self, call):
        with self.assertRaises(TypeError) as context:
            call()
        self.assertIn("search_path", str(context.exception))

    def test_bytes_search_path_rejected(self):
        with self.assertRaises(TypeError):
            is_tryexec_available("sh", search_path=b"/usr/bin:/bin")

    def test_container_search_paths_rejected(self):
        for value in WRONG_PATHS[:-1]:
            with self.subTest(value=value):
                self.assert_controlled_type_error(
                    lambda v=value: is_tryexec_available(
                        "sh", search_path=v))

    def test_bytes_search_path_rejected_for_container_call(self):
        with self.assertRaises(TypeError):
            tryexec_available_for_entry(
                {"TryExec": "sh"}, search_path=b"/usr/bin:/bin")

    def test_container_search_paths_rejected_for_entry(self):
        for value in WRONG_PATHS[:-1]:
            with self.subTest(value=value):
                self.assert_controlled_type_error(
                    lambda v=value: tryexec_available_for_entry(
                        {"TryExec": "sh"}, search_path=v))


class ControlTests(unittest.TestCase):
    """Existing valid behavior must survive the new validation."""

    def test_none_search_path_still_uses_host_path(self):
        self.assertIsInstance(is_tryexec_available("sh"), bool)

    def test_str_search_path_still_works(self):
        self.assertIs(
            is_tryexec_available("definitely-not-real-tryexec-xyz",
                                 search_path="/usr/bin:/bin"),
            False)

    def test_empty_str_search_path_still_works(self):
        self.assertIs(
            is_tryexec_available("sh", search_path=""),
            False)

    def test_no_probe_values_ignore_search_path(self):
        self.assertIs(is_tryexec_available(None, search_path=7), True)
        self.assertIs(is_tryexec_available("", search_path=7), True)

    def test_tryexec_wrong_type_error_is_unchanged(self):
        with self.assertRaises(TypeError) as context:
            is_tryexec_available(7)
        self.assertIn("TryExec", str(context.exception))

    def test_nul_and_field_codes_still_refused(self):
        self.assertIs(is_tryexec_available("sh\x00evil"), False)
        self.assertIs(is_tryexec_available("%f"), False)

    def test_entry_without_values_mapping_still_rejected(self):
        with self.assertRaises(TypeError):
            tryexec_available_for_entry(7)


if __name__ == "__main__":
    unittest.main()
