"""Offline unit tests for safe Desktop Entry Exec field-code parsing.

No shell, no process execution, no Qt runtime. Metacharacter inputs are used
as data only: a passing test proves they stayed literal inside argv.
"""
from pathlib import Path
import re
import unittest

from canopy_features.launcher import desktop_exec_fields as exec_fields


ROOT = Path(__file__).resolve().parents[1]


class ParseExecBasicTests(unittest.TestCase):
    def test_plain_command_and_quoted_argument(self):
        self.assertEqual(
            exec_fields.parse_exec('myapp --title "Hello World" /tmp/a.txt'),
            ["myapp", "--title", "Hello World", "/tmp/a.txt"],
        )

    def test_quotes_may_be_adjacent_to_text(self):
        self.assertEqual(
            exec_fields.parse_exec('myapp --name="Big App"'),
            ["myapp", "--name=Big App"],
        )

    def test_empty_quoted_argument_is_preserved(self):
        self.assertEqual(exec_fields.parse_exec('myapp "" tail'),
                         ["myapp", "", "tail"])

    def test_quote_escape_inside_quotes_only(self):
        self.assertEqual(
            exec_fields.parse_exec(r'myapp "say \"hi\""'),
            ["myapp", 'say "hi"'],
        )

    def test_backslash_is_literal_not_a_shell_escape(self):
        # Spec: any backslash other than \" inside quotes is literal.
        self.assertEqual(exec_fields.parse_exec(r'myapp a\bc "d\ef"'),
                         ["myapp", r"a\bc", r"d\ef"])

    def test_tabs_separate_arguments(self):
        self.assertEqual(exec_fields.parse_exec("myapp\t--flag\tvalue"),
                         ["myapp", "--flag", "value"])

    def test_unterminated_quote_rejected(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "unterminated"):
            exec_fields.parse_exec('myapp "broken')

    def test_empty_exec_rejected(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "empty"):
            exec_fields.parse_exec("   ")

    def test_non_string_exec_rejected(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "must be a string"):
            exec_fields.parse_exec(["myapp"])


class FieldCodeTests(unittest.TestCase):
    def test_single_file_code(self):
        self.assertEqual(
            exec_fields.parse_exec("myapp %f", fields={"f": "/tmp/a b.txt"}),
            ["myapp", "/tmp/a b.txt"],
        )

    def test_list_file_codes_expand_to_many_arguments(self):
        self.assertEqual(
            exec_fields.parse_exec("myapp %F", fields={"F": ["/tmp/a", "/tmp/b"]}),
            ["myapp", "/tmp/a", "/tmp/b"],
        )

    def test_empty_list_code_expands_to_nothing(self):
        self.assertEqual(exec_fields.parse_exec("myapp %U", fields={"U": []}),
                         ["myapp"])

    def test_url_codes(self):
        self.assertEqual(
            exec_fields.parse_exec("myapp %u %U", fields={
                "u": "https://example.test/a",
                "U": ["https://example.test/b", "file:///tmp/c"],
            }),
            ["myapp", "https://example.test/a",
             "https://example.test/b", "file:///tmp/c"],
        )

    def test_all_other_single_codes(self):
        for code in "dnckv":
            with self.subTest(code=code):
                self.assertEqual(
                    exec_fields.parse_exec("myapp %" + code, fields={code: "V"}),
                    ["myapp", "V"],
                )

    def test_all_other_list_codes(self):
        for code in "DNm":
            with self.subTest(code=code):
                self.assertEqual(
                    exec_fields.parse_exec("myapp %" + code, fields={code: ["A", "B"]}),
                    ["myapp", "A", "B"],
                )

    def test_icon_code_expands_to_two_arguments(self):
        self.assertEqual(
            exec_fields.parse_exec("myapp %i", fields={"i": "canopy"}),
            ["myapp", "--icon", "canopy"],
        )

    def test_empty_or_missing_icon_expands_to_nothing(self):
        self.assertEqual(exec_fields.parse_exec("myapp %i", fields={"i": ""}),
                         ["myapp"])
        self.assertEqual(exec_fields.parse_exec("myapp %i"), ["myapp"])

    def test_percent_escape(self):
        self.assertEqual(exec_fields.parse_exec("myapp 100%% done"),
                         ["myapp", "100%", "done"])

    def test_embedded_single_code(self):
        self.assertEqual(
            exec_fields.parse_exec("myapp --file=%f --tag=x", fields={"f": "a"}),
            ["myapp", "--file=a", "--tag=x"],
        )

    def test_field_code_inside_quotes_is_expanded_as_data(self):
        self.assertEqual(
            exec_fields.parse_exec('myapp "%f"', fields={"f": "a b"}),
            ["myapp", "a b"],
        )

    def test_missing_field_value_fails_closed(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "missing"):
            exec_fields.parse_exec("myapp %f")

    def test_embedded_list_code_rejected(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "embedded"):
            exec_fields.parse_exec("myapp --files=%F", fields={"F": ["a"]})

    def test_embedded_icon_code_rejected(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "whole argument"):
            exec_fields.parse_exec("myapp --icon=%i", fields={"i": "x"})

    def test_wrong_value_type_rejected(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "must be a string"):
            exec_fields.parse_exec("myapp %f", fields={"f": 42})


class UnsupportedFieldCodeTests(unittest.TestCase):
    def test_reserved_and_unknown_codes_rejected(self):
        for code in "tpqwxyzg123AB":
            with self.subTest(code=code):
                with self.assertRaisesRegex(exec_fields.ExecParseError,
                                            "unsupported field code"):
                    exec_fields.parse_exec("myapp %" + code)

    def test_trailing_percent_rejected(self):
        with self.assertRaisesRegex(exec_fields.ExecParseError, "truncated"):
            exec_fields.parse_exec("myapp 50%")

    def test_supported_code_set_is_exact(self):
        self.assertEqual(exec_fields.SUPPORTED_FIELD_CODES,
                         frozenset("fFuUdDnNickvm"))


class MetacharacterInjectionTests(unittest.TestCase):
    def test_shell_metacharacters_in_exec_stay_literal(self):
        result = exec_fields.parse_exec(
            "myapp $HOME `whoami` $(id) *.txt > out 2>&1 ; rm -rf / | &"
        )
        self.assertEqual(result, [
            "myapp", "$HOME", "`whoami`", "$(id)", "*.txt", ">",
            "out", "2>&1", ";", "rm", "-rf", "/", "|", "&",
        ])

    def test_metacharacter_literal_inside_quoted_argument(self):
        result = exec_fields.parse_exec('myapp "a; b && c | d"')
        self.assertEqual(result, ["myapp", "a; b && c | d"])

    def test_field_value_is_never_reparsed_as_shell(self):
        payload = "$(touch /tmp/pwned); `id` && rm -rf / > /dev/null"
        self.assertEqual(
            exec_fields.parse_exec("myapp %f", fields={"f": payload}),
            ["myapp", payload],
        )

    def test_quotes_and_slashes_in_field_value_stay_literal(self):
        payload = '"quoted" \\ $HOME; / bin'
        self.assertEqual(
            exec_fields.parse_exec("myapp %f", fields={"f": payload}),
            ["myapp", payload],
        )

    def test_control_characters_in_field_value_rejected(self):
        for bad in ("a\x00b", "a\nb", "a\rb"):
            with self.subTest(value=repr(bad)):
                with self.assertRaisesRegex(exec_fields.ExecParseError,
                                            "control character"):
                    exec_fields.parse_exec("myapp %f", fields={"f": bad})


class NoShellSourceTests(unittest.TestCase):
    def test_module_never_imports_or_calls_a_shell(self):
        source = (ROOT / "canopy_features" / "launcher"
                  / "desktop_exec_fields.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "shell=True", "popen",
                          "shlex", "eval(", "__import__"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)
        # Bare builtin exec(), not the substring in parse_exec().
        self.assertIsNone(re.search(r"\bexec\s*\(", source))


if __name__ == "__main__":
    unittest.main()
