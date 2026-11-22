"""Safety tests for the optional Mint guest runtime orchestrator.

No real VM, VBoxManage, SSH or Mint guest is used. A green unit test is never
Mint guest acceptance; a real guest run with recorded command, exit status
and authentic logs is required for that.
"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools import mint_classic_qt_smoke as qt
from tools import mint_guest_preflight as preflight
from tools.qa import classic_mint_guest_runtime as runtime


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "a" * 40
READY_JSON = json.dumps({
    "schema_version": 1,
    "probe_only": True,
    "mint_identified": True,
    "status": "READY_FOR_TESTS",
    "session_type": "x11",
}).encode("utf-8")
UBUNTU_JSON = json.dumps({
    "probe_only": True,
    "mint_identified": False,
    "status": "BLOCKED",
}).encode("utf-8")
VMS = b'"MintGuest" {11111111-1111-1111-1111-111111111111}\n'


class Result:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def which_for(available):
    def which(name):
        return "/usr/bin/" + name if name in available else None
    return which


class QueueRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, timeout):
        self.calls.append((list(argv), timeout))
        if not self.results:
            return Result(0, b"", b"")
        item = self.results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class RuntimeHelpersTests(unittest.TestCase):
    def test_validate_timeout_uses_exact_int_and_bounds(self):
        self.assertEqual(runtime.validate_timeout(30), 30)
        for value in (0, runtime.MAX_TIMEOUT + 1, 2.5, True, False, "10", None):
            with self.subTest(value=value):
                with self.assertRaises(runtime.RuntimeSafetyError):
                    runtime.validate_timeout(value)

    def test_validate_guest_path_rejects_relative_and_unsafe_paths(self):
        bad = [
            "relative/path", "", "../etc", "/a/../b", "/a b",
            "/a;b", "/a$(id)", "/a`id`", "/a\\b", "/a'b",
            "/a\x00b", "/" + "x" * (runtime.MAX_PATH_LENGTH + 1),
        ]
        for value in bad:
            with self.subTest(value=value[:40]):
                with self.assertRaises(runtime.RuntimeSafetyError):
                    runtime.validate_guest_path(value, "path")
        self.assertEqual(
            runtime.validate_guest_path("/opt/canopy/bin/qt", "binary"),
            "/opt/canopy/bin/qt",
        )

    def test_validate_source_sha_matches_existing_tool_rule(self):
        self.assertEqual(runtime.validate_source_sha(SOURCE), SOURCE)
        self.assertIs(runtime.qt.SHA40, qt.SHA40)
        for value in ("abc", "A" * 40, "g" * 40, SOURCE + "x", None):
            with self.subTest(value=value):
                with self.assertRaises(runtime.RuntimeSafetyError):
                    runtime.validate_source_sha(value)

    def test_vbox_command_allowlist_blocks_modifying_operations(self):
        self.assertEqual(
            runtime.vbox_command("list", "vms"), ["VBoxManage", "list", "vms"],
        )
        self.assertEqual(
            runtime.vbox_command("showvminfo", "MintGuest", "--machinereadable"),
            ["VBoxManage", "showvminfo", "MintGuest", "--machinereadable"],
        )
        for verb in ("startvm", "controlvm", "modifyvm", "snapshot", "import"):
            with self.subTest(verb=verb):
                with self.assertRaisesRegex(runtime.RuntimeSafetyError, "not allowed"):
                    runtime.vbox_command(verb, "MintGuest")

    def test_ssh_command_forces_noninteractive_and_never_reads_password(self):
        argv = runtime.ssh_command("192.168.1.10", "tester", "echo hi", 7)
        tokens = [token.lower() for token in argv]
        self.assertIn("batchmode=yes", tokens)
        self.assertIn("passwordauthentication=no", tokens)
        self.assertIn("kbdinteractiveauthentication=no", tokens)
        self.assertIn("connecttimeout=7", tokens)
        self.assertIn("--", argv)
        self.assertEqual(argv[-1], "echo hi")
        self.assertEqual(argv[argv.index("--") - 1], "tester@192.168.1.10")
        self.assertFalse(any("password=" in token for token in tokens))
        self.assertFalse(any("sshpass" in token or "expect" in token for token in tokens))

    def test_ssh_command_validates_host_and_user(self):
        for host, user in (("bad host", None), ("-o", None), ("h", "bad user"),
                           ("h", "root;x"), ("", None)):
            with self.subTest(host=host, user=user):
                with self.assertRaises(runtime.RuntimeSafetyError):
                    runtime.ssh_command(host, user, "echo hi", 5)
        with self.assertRaises(runtime.RuntimeSafetyError):
            runtime.ssh_command("host", None, "", 5)
        with self.assertRaises(runtime.RuntimeSafetyError):
            runtime.ssh_command("host", None, "echo hi", 9999)

    def test_guest_module_command_reuses_repository_tool_modules(self):
        remote = runtime.guest_module_command(
            "/home/tester/canopy", preflight, "--json",
        )
        self.assertIn("cd /home/tester/canopy && python3 -m tools.mint_guest_preflight", remote)
        self.assertIn("--json", remote)
        smoke_remote = runtime.guest_module_command(
            "/home/tester/canopy", qt, "--binary", "/opt/qt/bin", "--source-sha", SOURCE,
        )
        self.assertIn("python3 -m tools.mint_classic_qt_smoke", smoke_remote)
        self.assertIn(SOURCE, smoke_remote)
        self.assertEqual(preflight.collect.__module__, "tools.mint_guest_preflight")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.kwargs = {
            "guest_host": "192.168.1.10",
            "guest_user": "tester",
            "guest_repo_dir": "/home/tester/canopy",
            "binary": "/opt/canopy/canopy-classic",
            "art_dir": "/opt/canopy/assets/approved",
            "wallpaper": "/opt/canopy/alpine.png",
            "evidence_dir": "/tmp/canopy-mint-evidence",
            "source_sha": SOURCE,
        }
        self.both = which_for({runtime.VBOX_BIN, runtime.SSH_BIN})

    def plan(self, **changes):
        values = dict(self.kwargs)
        values.update(changes)
        return runtime.build_plan(which=self.both, runner=QueueRunner([Result(0, VMS)]), **values)

    def test_dry_run_is_default_and_never_executes(self):
        runner = QueueRunner([Result(0, VMS)])
        report = runtime.build_plan(which=self.both, runner=runner, **self.kwargs)
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["status"], runtime.DRY_RUN)
        self.assertIsNone(report["execution"])
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
        self.assertEqual(report["real_application_launch"], "NOT_RUN")
        self.assertEqual(report["visual_owner_approval"], "NOT_RUN")
        self.assertFalse(report["guest_ran_qt_binary"])
        self.assertFalse(report["authentic_logs_captured"])
        self.assertIsNotNone(report["commands"]["guest_preflight"])
        self.assertIsNotNone(report["commands"]["guest_smoke"])

    def test_discover_only_reports_not_run_when_guest_unavailable(self):
        report = runtime.discover_report(
            which=which_for(set()), runner=QueueRunner([]),
        )
        self.assertEqual(report["mode"], "discover")
        self.assertEqual(report["status"], runtime.DRY_RUN)
        self.assertFalse(report["host"]["vboxmanage"]["available"])
        self.assertFalse(report["host"]["ssh"]["available"])
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")

    def test_invalid_paths_rejected_before_any_command(self):
        for field in ("guest_repo_dir", "binary", "art_dir", "wallpaper", "evidence_dir"):
            for bad in ("relative", "/tmp/../x", "/tmp/a;b"):
                with self.subTest(field=field, bad=bad):
                    runner = QueueRunner([])
                    with self.assertRaises(runtime.RuntimeSafetyError):
                        runtime.build_plan(
                            which=self.both, runner=runner,
                            **dict(self.kwargs, **{field: bad}),
                        )
                    self.assertEqual(runner.calls, [])

    def test_invalid_timeout_and_source_sha_rejected(self):
        for timeout in (0, 301, True, 5.0):
            with self.subTest(timeout=timeout):
                with self.assertRaises(runtime.RuntimeSafetyError):
                    runtime.build_plan(
                        which=self.both, runner=QueueRunner([]),
                        **dict(self.kwargs, timeout=timeout),
                    )
        with self.assertRaises(runtime.RuntimeSafetyError):
            runtime.build_plan(
                which=self.both, runner=QueueRunner([]),
                **dict(self.kwargs, source_sha="not-a-sha"),
            )

    def test_invalid_mode_rejected(self):
        with self.assertRaises(runtime.RuntimeSafetyError):
            runtime.build_plan(
                which=self.both, runner=QueueRunner([]),
                **dict(self.kwargs, mode="force"),
            )

    def test_missing_configured_vm_is_a_blocker_not_an_error(self):
        report = self.plan(mode="execute", vbox_vm="NoSuchVM")
        self.assertIn("VM not found", " ".join(report["blockers"]))
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_discover_host_reads_vm_inventory_and_state(self):
        runner = QueueRunner([
            Result(0, VMS),
            Result(0, b'VMState="running"\n'),
        ])
        host = runtime.discover_host(
            which=self.both, runner=runner, vbox_vm="MintGuest",
        )
        self.assertEqual(host["vms"], [{
            "name": "MintGuest",
            "uuid": "11111111-1111-1111-1111-111111111111",
            "state": "running",
        }])
        self.assertTrue(
            all(call[0][1] in runtime.ALLOWED_VBOX_SUBCOMMANDS for call in runner.calls)
        )

    def test_host_discovery_errors_are_recorded_not_fatal(self):
        runner = QueueRunner([OSError("boom")])
        host = runtime.discover_host(which=self.both, runner=runner)
        self.assertTrue(any("list vms failed" in e for e in host["errors"]))

    def test_huge_vbox_output_is_not_trusted(self):
        runner = QueueRunner([Result(0, b"x" * (runtime.MAX_VBOX_BYTES + 1))])
        host = runtime.discover_host(which=self.both, runner=runner)
        self.assertEqual(host["vms"], [])
        self.assertTrue(any("safe limit" in e for e in host["errors"]))


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.kwargs = {
            "guest_host": "192.168.1.10",
            "guest_user": "tester",
            "guest_repo_dir": "/home/tester/canopy",
            "binary": "/opt/canopy/canopy-classic",
            "art_dir": "/opt/canopy/assets/approved",
            "wallpaper": "/opt/canopy/alpine.png",
            "evidence_dir": "/tmp/canopy-mint-evidence",
            "source_sha": SOURCE,
        }
        self.both = which_for({runtime.VBOX_BIN, runtime.SSH_BIN})

    def execute(self, results, which=None, vbox_vm=None, timeout=runtime.DEFAULT_TIMEOUT):
        runner = QueueRunner(results)
        report = runtime.build_plan(
            which=which or self.both, runner=QueueRunner([Result(0, VMS)]),
            mode="execute", vbox_vm=vbox_vm, **self.kwargs,
        )
        return runtime.run_plan(report, runner=runner, timeout=timeout), runner

    def happy_results(self, smoke_stdout=None, preflight=READY_JSON):
        return [
            Result(0, preflight),
            Result(0, smoke_stdout if smoke_stdout is not None
                   else runtime.SMOKE_PASS_MARKER.encode() + b"\n"),
        ]

    def test_absent_vboxmanage_and_ssh_reports_not_run(self):
        report, runner = self.execute([], which=which_for(set()))
        self.assertEqual(report["status"], runtime.BLOCKED)
        self.assertIs(report["execution"]["attempted"], False)
        self.assertTrue(any("VBoxManage" in b for b in report["blockers"]))
        self.assertTrue(any("ssh" in b for b in report["blockers"]))
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")
        self.assertEqual(runner.calls, [])

    def test_absent_ssh_only_reports_not_run(self):
        report, _ = self.execute([], which=which_for({runtime.VBOX_BIN}))
        self.assertFalse(report["execution"]["attempted"])
        self.assertTrue(any("ssh" in b for b in report["blockers"]))
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_happy_guest_run_captures_evidence_without_acceptance(self):
        report, runner = self.execute(self.happy_results())
        self.assertEqual(len(runner.calls), 2)
        execution = report["execution"]
        self.assertTrue(execution["attempted"])
        self.assertEqual(len(execution["steps"]), 2)
        preflight_step, smoke_step = execution["steps"]
        self.assertEqual(preflight_step["name"], "guest_preflight")
        self.assertEqual(smoke_step["name"], "guest_smoke")
        self.assertEqual(preflight_step["exit_code"], 0)
        self.assertEqual(smoke_step["exit_code"], 0)
        self.assertIn(runtime.SMOKE_PASS_MARKER, smoke_step["stdout"])
        self.assertTrue(preflight_step["preflight"]["mint_identified"])
        self.assertTrue(report["guest_ran_qt_binary"])
        self.assertTrue(report["authentic_logs_captured"])
        self.assertEqual(report["status"], runtime.EVIDENCE_PENDING)
        self.assertEqual(report["guest_runtime_acceptance"], runtime.EVIDENCE_PENDING)
        self.assertEqual(report["real_application_launch"], "PASS")
        self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
        self.assertEqual(report["visual_owner_approval"], "NOT_RUN")
        self.assertIsInstance(smoke_step["command"], list)
        self.assertIn("tools.mint_classic_qt_smoke", smoke_step["command"][-1])

    def test_non_mint_preflight_skips_qt_smoke(self):
        report, runner = self.execute(self.happy_results(preflight=UBUNTU_JSON))
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(len(report["execution"]["steps"]), 1)
        self.assertFalse(report["guest_ran_qt_binary"])
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_invalid_preflight_json_skips_qt_smoke(self):
        report, runner = self.execute(self.happy_results(preflight=b"not json"))
        self.assertEqual(len(runner.calls), 1)
        self.assertIsNone(report["execution"]["steps"][0]["preflight"])
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_preflight_timeout_skips_qt_smoke(self):
        report, runner = self.execute([
            subprocess.TimeoutExpired("ssh", 5),
        ])
        self.assertEqual(len(runner.calls), 1)
        step = report["execution"]["steps"][0]
        self.assertTrue(step["timed_out"])
        self.assertIn("timed out", step["error"])
        self.assertFalse(report["guest_ran_qt_binary"])
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_smoke_timeout_is_failure_not_false_success(self):
        report, _ = self.execute([
            Result(0, READY_JSON),
            subprocess.TimeoutExpired("ssh", 5),
        ])
        smoke_step = report["execution"]["steps"][1]
        self.assertTrue(smoke_step["timed_out"])
        self.assertFalse(report["guest_ran_qt_binary"])
        self.assertEqual(report["status"], runtime.FAIL)
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_smoke_nonzero_exit_is_not_success(self):
        report, _ = self.execute([
            Result(0, READY_JSON),
            Result(4, runtime.SMOKE_PASS_MARKER.encode()),
        ])
        self.assertEqual(report["execution"]["steps"][1]["exit_code"], 4)
        self.assertFalse(report["guest_ran_qt_binary"])
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_smoke_without_pass_marker_is_not_success(self):
        report, _ = self.execute([
            Result(0, READY_JSON),
            Result(0, b"Qt exited but no self-test marker\n"),
        ])
        self.assertFalse(report["execution"]["steps"][1]["smoke_pass_marker"])
        self.assertFalse(report["guest_ran_qt_binary"])
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_oserror_is_recorded_without_claiming_acceptance(self):
        report, _ = self.execute([Result(0, READY_JSON), OSError("gone")])
        step = report["execution"]["steps"][1]
        self.assertIn("command failed to start", step["error"])
        self.assertEqual(step["exit_code"], None)
        self.assertEqual(report["guest_runtime_acceptance"], "NOT_RUN")

    def test_logs_are_bounded_and_flagged(self):
        huge = runtime.SMOKE_PASS_MARKER.encode() + b"x" * (runtime.MAX_LOG_BYTES + 500)
        report, _ = self.execute(self.happy_results(smoke_stdout=huge))
        smoke_step = report["execution"]["steps"][1]
        self.assertTrue(smoke_step["logs_truncated"])
        self.assertLessEqual(len(smoke_step["stdout"]), runtime.MAX_LOG_BYTES)
        self.assertEqual(report["guest_runtime_acceptance"], runtime.EVIDENCE_PENDING)

    def test_run_plan_ignores_non_execute_modes(self):
        report = runtime.build_plan(
            which=self.both, runner=QueueRunner([Result(0, VMS)]), **self.kwargs,
        )
        result = runtime.run_plan(report, runner=QueueRunner([]))
        self.assertIsNone(result["execution"])
        self.assertEqual(result["mode"], "dry-run")


class CliTests(unittest.TestCase):
    def base_args(self):
        return [
            "--guest-host", "192.168.1.10",
            "--guest-repo-dir", "/home/tester/canopy",
            "--binary", "/opt/canopy/canopy-classic",
            "--approved-art-dir", "/opt/canopy/assets/approved",
            "--landscape-wallpaper", "/opt/canopy/alpine.png",
            "--evidence-dir", "/tmp/canopy-mint-evidence",
            "--source-sha", SOURCE,
        ]

    def test_cli_discover_only_without_guest_is_zero_and_not_run(self):
        buffer = io.StringIO()
        with patch.object(runtime, "_which", which_for(set())), \
                patch.object(runtime, "_run", QueueRunner([])), \
                contextlib.redirect_stdout(buffer):
            code = runtime.main(["--discover-only", "--json"])
        self.assertEqual(json.loads(buffer.getvalue())[
            "mint_guest_acceptance"], "NOT_RUN")
        self.assertEqual(code, 0)

    def test_cli_dry_run_requires_guest_arguments(self):
        with contextlib.redirect_stderr(io.StringIO()):
            code = runtime.main([])
        self.assertEqual(code, 2)

    def test_cli_rejects_unsafe_path(self):
        args = self.base_args()
        args[args.index("/opt/canopy/canopy-classic")] = "relative/binary"
        with contextlib.redirect_stderr(io.StringIO()):
            code = runtime.main(args)
        self.assertEqual(code, 2)

    def test_cli_execute_end_to_end_with_fake_guest(self):
        runner = QueueRunner([
            Result(0, VMS), Result(0, READY_JSON),
            Result(0, runtime.SMOKE_PASS_MARKER.encode() + b"\n"),
        ])
        buffer = io.StringIO()
        with patch.object(runtime, "_which", which_for(
                {runtime.VBOX_BIN, runtime.SSH_BIN})), \
                patch.object(runtime, "_run", runner), \
                contextlib.redirect_stdout(buffer):
            code = runtime.main(self.base_args() + ["--execute", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue())[
            "guest_runtime_acceptance"], runtime.EVIDENCE_PENDING)
        self.assertEqual(len(runner.calls), 3)

    def test_cli_guest_unavailable_is_zero_with_not_run(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = runtime.main(["--discover-only"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
