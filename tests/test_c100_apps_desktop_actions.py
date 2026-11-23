"""Offline unit tests for desktop action parsing and validation.

Text-level tests only. No Qt, GIO, Linux Mint or desktop session is exercised.
"""

import unittest

from canopy_features.apps.desktop_actions import (
    MAX_ACTIONS,
    is_valid_action_id,
    parse_desktop_actions,
)


def _entry(actions="", groups=""):
    return "[Desktop Entry]\nType=Application\nName=Demo\nActions=%s;\n%s" % (
        actions, groups)


def _codes(scan):
    return [problem.code for problem in scan.problems]


class ActionIdValidation(unittest.TestCase):
    def test_valid_ids(self):
        for value in ("new-window", "NewWindow", "a.b", "x@y", "a_b",
                      "a" * 128, "0"):
            with self.subTest(value=value):
                self.assertTrue(is_valid_action_id(value))

    def test_invalid_ids(self):
        for value in ("", "has space", "semi;colon", "slash/id", "[bracket]",
                      "eq=sign", "café", "a" * 129, None, 7):
            with self.subTest(value=value):
                self.assertFalse(is_valid_action_id(value))


class DesktopActionParsing(unittest.TestCase):
    def test_valid_entry_parses_actions(self):
        text = _entry(
            actions="new-window;new-private-window;",
            groups=(
                "[Desktop Action new-window]\n"
                "Name=New Window\n"
                "Exec=demo --new-window\n"
                "Icon=demo\n"
                "\n"
                "[Desktop Action new-private-window]\n"
                "Name=New Private Window\n"
                "Exec=demo --private\n"
            ),
        )
        scan = parse_desktop_actions(text)
        self.assertTrue(scan.ok, scan.problems)
        self.assertEqual(scan.declared_ids,
                         ("new-window", "new-private-window"))
        self.assertEqual(len(scan.actions), 2)
        first = scan.actions[0]
        self.assertEqual(first.action_id, "new-window")
        self.assertEqual(first.name, "New Window")
        self.assertEqual(first.exec_line, "demo --new-window")
        self.assertEqual(first.icon, "demo")
        self.assertEqual(scan.actions[1].icon, "")

    def test_empty_text_has_no_actions_or_problems(self):
        scan = parse_desktop_actions("")
        self.assertTrue(scan.ok)
        self.assertEqual(scan.actions, ())
        self.assertEqual(scan.declared_ids, ())

    def test_comments_and_locale_keys_are_ignored(self):
        text = (
            "# leading comment\n"
            "[Desktop Entry]\n"
            "actions=new-window;\n"  # case-sensitive key must be ignored
            "Actions=new-window;\n"
            "\n"
            "[Desktop Action new-window]\n"
            "Name=New Window\n"
            "Name[fr]=Nouvelle fenêtre\n"
            "Exec=demo --new-window\n"
        )
        scan = parse_desktop_actions(text)
        self.assertTrue(scan.ok, scan.problems)
        self.assertEqual(scan.declared_ids, ("new-window",))
        self.assertEqual(scan.actions[0].name, "New Window")

    def test_non_string_input_raises(self):
        with self.assertRaises(TypeError):
            parse_desktop_actions(None)


class DesktopActionValidation(unittest.TestCase):
    def test_missing_group_reference(self):
        scan = parse_desktop_actions(_entry(actions="missing-action"))
        self.assertFalse(scan.ok)
        self.assertIn("missing-group", _codes(scan))
        self.assertEqual(scan.actions, ())

    def test_missing_group_for_one_of_several_declarations(self):
        text = _entry(
            actions="open;missing;",
            groups="[Desktop Action open]\nExec=demo --open\n",
        )
        scan = parse_desktop_actions(text)
        self.assertEqual(_codes(scan), ["missing-group"])

    def test_duplicate_declared_action_name(self):
        scan = parse_desktop_actions(_entry(actions="open;open;"))
        self.assertFalse(scan.ok)
        self.assertIn("duplicate-action", _codes(scan))
        self.assertEqual(scan.declared_ids, ("open", "open"))

    def test_duplicate_group_heading(self):
        text = _entry(
            actions="open;",
            groups=(
                "[Desktop Action open]\nExec=demo --one\n"
                "[Desktop Action open]\nExec=demo --two\n"
            ),
        )
        scan = parse_desktop_actions(text)
        self.assertFalse(scan.ok)
        self.assertIn("duplicate-action", _codes(scan))
        self.assertEqual(len(scan.actions), 1)

    def test_orphan_group(self):
        text = _entry(groups="[Desktop Action unused]\nExec=demo --unused\n")
        scan = parse_desktop_actions(text)
        self.assertEqual(_codes(scan), ["orphan-group"])
        self.assertEqual(len(scan.actions), 1)

    def test_id_typo_reports_missing_and_orphan_together(self):
        text = _entry(
            actions="opne;",
            groups="[Desktop Action open]\nExec=demo --open\n",
        )
        scan = parse_desktop_actions(text)
        self.assertCountEqual(_codes(scan), ["missing-group", "orphan-group"])

    def test_invalid_declared_and_group_ids(self):
        text = _entry(
            actions="bad id;",
            groups="[Desktop Action bad/id]\nExec=demo --bad\n",
        )
        scan = parse_desktop_actions(text)
        self.assertEqual(_codes(scan).count("invalid-id"), 2)

    def test_missing_exec(self):
        text = _entry(
            actions="open;",
            groups="[Desktop Action open]\nName=Open\n",
        )
        scan = parse_desktop_actions(text)
        self.assertIn("missing-exec", _codes(scan))

    def test_action_count_is_bounded(self):
        declared = ";".join("action%02d" % i for i in range(MAX_ACTIONS + 3))
        scan = parse_desktop_actions(_entry(actions=declared))
        self.assertEqual(len(scan.declared_ids), MAX_ACTIONS)
        self.assertIn("too-many-actions", _codes(scan))


if __name__ == "__main__":
    unittest.main()
