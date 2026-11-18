"""Headless tests for the VM test controller."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.mint_testlab import COMMANDS, execute, gtk_readiness, run_check


class TestLabTests(unittest.TestCase):
    def test_success_and_failure(self):
        with tempfile.TemporaryDirectory() as root:
            executor = lambda *_args, **_kw: subprocess.CompletedProcess(COMMANDS['unit'], 0, 'ok', '')
            result = run_check('unit', COMMANDS['unit'], root, 4,
                               executor=executor, which=lambda _: '/usr/bin/python3')
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['output'], 'ok')
            executor = lambda *_args, **_kw: subprocess.CompletedProcess(COMMANDS['unit'], 2, '', 'broken')
            result = run_check('unit', COMMANDS['unit'], root, 4,
                               executor=executor, which=lambda _: 'python')
            self.assertEqual(result['status'], 'FAIL')

    def test_missing_executable(self):
        result = run_check('gtk', COMMANDS['gtk'], '.', 4, which=lambda _: None)
        self.assertEqual(result['status'], 'BLOCKED')

    def test_gtk_requires_real_display_probe(self):
        invocations = []
        def executor(command, **_kwargs):
            invocations.append(command)
            if "-c" in command:
                return subprocess.CompletedProcess(command, 3, "", "no display")
            return subprocess.CompletedProcess(command, 0, "Ran 30 tests", "")
        ready = run_check("gtk", COMMANDS["gtk"], ".", 30,
                          executor=executor, which=lambda _: "/usr/bin/tool")
        self.assertEqual(ready["status"], "BLOCKED")
        self.assertIn("display", ready["reason"])
        self.assertEqual(len(invocations), 1)

    def test_gtk_success_requires_probe_and_test_execution(self):
        calls = []
        def executor(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "OK", "")
        outcome = run_check("gtk", COMMANDS["gtk"], ".", 30,
                            executor=executor, which=lambda _: "/usr/bin/tool")
        self.assertEqual(outcome["status"], "PASS")
        self.assertEqual(len(calls), 2)
        self.assertIn("-c", calls[0])
        self.assertIn("unittest", calls[1])

    def test_gtk_missing_gi_dependency_is_blocked(self):
        self.assertIn("xauth", gtk_readiness(
            30, which=lambda program: None if program == "xauth" else "/bin/tool"))
        self.assertIn("TimeoutExpired", gtk_readiness(
            30, which=lambda _: "/bin/tool",
            executor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("gtk", 4))))

    def test_timeout_handles_bytes_and_text(self):
        def timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired('python3', 3, output=b'late', stderr='error')
        result = run_check('unit', COMMANDS['unit'], '.', 3,
                           executor=timeout, which=lambda _: 'python')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['reason'], 'TIMEOUT')
        self.assertIn('lateerror', result['output'])

    def test_report_and_status_priority(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'canopy').mkdir()
            (root / 'canopy/__init__.py').touch()
            (root / 'tests').mkdir()
            output = root / 'reports' / 'result.json'
            def fake(name, *_):
                return {'name': name, 'status': {
                    'unit': 'PASS', 'syntax': 'BLOCKED', 'gtk': 'FAIL'}[name]}
            report = execute(root, output, ['unit', 'syntax', 'gtk'], runner=fake)
            self.assertEqual(report['status'], 'FAIL')
            self.assertEqual(json.loads(output.read_text())['status'], 'FAIL')
            self.assertFalse(output.with_name('result.json.tmp').exists())

    def test_reject_bad_root_and_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                execute(d, Path(d) / 'out.json', ['unit'])
            root = Path(d)
            (root / 'canopy').mkdir()
            (root / 'canopy/__init__.py').touch()
            (root / 'tests').mkdir()
            with self.assertRaises(ValueError):
                execute(root, root / 'out.json', ['unit'], timeout=0)


if __name__ == '__main__':
    unittest.main()
