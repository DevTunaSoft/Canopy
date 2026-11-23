"""Wrong-type shortcut registrations must fail closed with the domain error.

Pure in-memory validator; no Qt, compositor, OS key map or desktop service is
read. The public entry point documents ShortcutConflictError for bad input, so
a non-iterable ``shell``/``user`` must not leak a bare TypeError from ``for``.
"""
import unittest

from canopy_features.accessibility.shortcut_conflict_check import (
    ShortcutConflictError,
    detect_shortcut_conflicts,
)


class ShortcutRegistrationWrongTypeTests(unittest.TestCase):
    def test_non_iterable_shell_registrations_fail_closed(self):
        for value in (None, 7, 3.5):
            with self.subTest(value=value):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(shell=value)

    def test_non_iterable_user_registrations_fail_closed(self):
        for value in (None, True, 7, 3.5):
            with self.subTest(value=value):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(user=value)

    def test_both_sources_wrong_type_fail_closed(self):
        for shell, user in ((None, None), (7, 3.5), (None, 7)):
            with self.subTest(shell=shell, user=user):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(shell=shell, user=user)

    def test_error_is_domain_error_with_documented_message(self):
        with self.assertRaises(ShortcutConflictError) as ctx:
            detect_shortcut_conflicts(shell=None)
        self.assertIn("iterable of pairs", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, TypeError)

    def test_string_and_bytes_registrations_still_refused(self):
        for value in ("Ctrl+A", b"Ctrl+A"):
            with self.subTest(value=value):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(shell=value)
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(user=value)

    def test_valid_iterables_and_other_guards_unchanged(self):
        # Controls: tuple/list/generator registrations and the reserved-set
        # guard must behave exactly as before the fix.
        self.assertTrue(detect_shortcut_conflicts(shell=()).ok)
        self.assertTrue(detect_shortcut_conflicts(user=[]).ok)
        gen = (("files.close", "Ctrl+W") for _ in range(1))
        self.assertTrue(detect_shortcut_conflicts(shell=gen).ok)
        report = detect_shortcut_conflicts(
            shell=[("files.close", "Ctrl+W")],
            user=[("custom.open", "ctrl+w")],
        )
        self.assertEqual(len(report.of_kind("collision")), 1)
        for value in (None, 7, "Ctrl+A"):
            with self.subTest(reserved=value):
                with self.assertRaises(ShortcutConflictError):
                    # Deliberately wrong type to exercise the fail-closed guard.
                    detect_shortcut_conflicts(reserved=value)  # type: ignore[arg-type]
        # An iterable of non-pairs is refused with the domain error too.
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell={"a": 1})
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell=[["only-one"]])


if __name__ == "__main__":
    unittest.main()
