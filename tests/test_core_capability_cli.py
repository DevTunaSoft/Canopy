"""Contract tests for the inert capability-report CLI (stdout only)."""
import ast
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError
import io
import json
from pathlib import Path
import unittest

from canopy_core import capability_cli as cli
from canopy_core.shell_host import HostCapabilityReport

EXPECTED_TOKENS = ["BLOCKED", "READINESS_SNAPSHOT", "SNAPSHOT", "IDLE",
                   "BLOCKED", "BLOCKED", "BLOCKED", "DENIED"]


def run_cli(argv=None):
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


class CapabilityCliTests(unittest.TestCase):
    def test_stdout_is_bounded_fixed_fields_only(self):
        code, text = run_cli()
        self.assertEqual(code, 0)
        data = json.loads(text)
        self.assertEqual(frozenset(data), frozenset(cli.OUTPUT_KEYS))
        self.assertEqual(data["status"], "CAPABILITY_REPORT")
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["component_count"], 8)
        self.assertEqual(data["component_tokens"], EXPECTED_TOKENS)
        for key in cli.NEGATIVE_CLAIMS:
            self.assertIs(data[key], False)

    def test_no_host_state_fields_in_output(self):
        _, text = run_cli()
        self.assertNotIn("has_active_pack", text)
        self.assertNotIn("needs_recovery", text)

    def test_no_raw_value_echo(self):
        _, text = run_cli()
        for marker in ("C:\\", "/home", "SECRET", "PackScan", "ShellHost"):
            self.assertNotIn(marker, text)

    def test_deterministic_repeated_calls(self):
        self.assertEqual(run_cli()[1], run_cli()[1])
        self.assertEqual(run_cli()[1], run_cli()[1])

    def test_report_is_frozen_and_typed(self):
        report = cli.build_report()
        self.assertIsInstance(report, HostCapabilityReport)
        with self.assertRaises(FrozenInstanceError):
            report.component_count = 0

    def test_inert_records_are_eight_and_fresh(self):
        first = cli.inert_records()
        second = cli.inert_records()
        self.assertEqual(frozenset(first), frozenset({
            "schema", "reliability", "readiness", "security", "launch",
            "focus", "session", "recovery", "desktop"}))
        self.assertEqual(first, second)
        first["desktop"]["status"] = "APPROVED"
        self.assertEqual(second["desktop"]["status"], "DENIED")

    def test_arguments_rejected_without_output(self):
        code, text = run_cli(["anything"])
        self.assertEqual(code, 2)
        self.assertEqual(text, "")

    def test_module_entrypoint_guard(self):
        source = Path(cli.__file__).read_text(encoding="utf-8")
        self.assertIn('if __name__ == "__main__":', source)
        self.assertIn("raise SystemExit(main())", source)


class CliPurityTests(unittest.TestCase):
    def test_no_io_beyond_stdout_or_lifecycle_imports(self):
        tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
        allowed_imports = {"json", "canopy_core", "__future__"}
        forbidden_calls = {"open", "input", "Popen", "popen", "system",
                           "sleep", "subscribe", "emit", "scan_shell_packs"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0], allowed_imports)
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if node.level:
                    self.assertIn(module, {"registry", "shell_host"})
                else:
                    self.assertIn(module, allowed_imports)
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) \
                    else getattr(node.func, "id", "")
                self.assertNotIn(name, forbidden_calls)
        self.assertIn("print", {getattr(n.func, "id", "")
                                for n in ast.walk(tree)
                                if isinstance(n, ast.Call)})


if __name__ == "__main__":
    unittest.main()
