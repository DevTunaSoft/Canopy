"""No-network tests for opt-in, unprivileged Canopy Windows autostart."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from canopy_supervisor import state
from canopy_supervisor.supervisor import DEFAULT_CONFIG
from tools import canopy_autopilot as auto


def result(code=0, output=""):
    return SimpleNamespace(returncode=code, stdout=output, stderr="")


class AutopilotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "state"
        self.checkout = self.base / "checkout"
        (self.checkout / ".git").mkdir(parents=True)
        self.root.mkdir()
        self.app = self.base / "app folder"
        self.pyw = self.base / "Program Files" / "pythonw.exe"
        self.pyw.parent.mkdir()
        self.pyw.write_text("synthetic exe marker", encoding="utf-8")
        self.store = state.TaskStore(self.root)
        state.atomic_write(
            self.store.config_path,
            json.dumps({**DEFAULT_CONFIG, "repo": str(self.checkout),
                        "state_root": str(self.root)}),
        )
        self.calls = []
        self.launches = []

    def fake_runner(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        return result()

    def fake_popen(self, args, **kwargs):
        self.launches.append((list(args), kwargs))
        return object()

    def install(self):
        return auto.install(
            self.root, self.checkout, runner=self.fake_runner,
            popen=self.fake_popen, pythonexe=self.pyw, appdata=self.app,
        )

    def test_scheduler_command_has_no_shell_or_elevation(self):
        value = auto.scheduled_command(
            self.pyw.resolve(), (self.app / "Canopy-Watchdog.pyw").resolve(),
            (self.app / "autopilot.json").resolve(),
        )
        self.assertIn("pythonw.exe", value)
        self.assertIn('"', value)
        self.assertNotIn("cmd.exe", value)
        auto.scheduler_create(auto.task_name(self.root), value,
                              runner=self.fake_runner)
        invocation, keyword = self.calls[-1]
        self.assertEqual(invocation[0], "schtasks.exe")
        self.assertEqual(invocation[1], "/Create")
        self.assertIn("/RL", invocation)
        self.assertIn("LIMITED", invocation)
        self.assertNotIn("/RP", invocation)
        self.assertNotIn("HIGHEST", invocation)
        self.assertNotIn("/RU", invocation)
        self.assertEqual(keyword["timeout"], 45)

    def test_install_writes_one_unprivileged_recovery_task(self):
        settings = self.install()
        self.assertTrue(settings.exists())
        self.assertEqual(auto.load_settings(settings)["checkout"],
                         str(self.checkout.resolve()))
        self.assertTrue((self.app / "Canopy-Watchdog.pyw").exists())
        self.assertEqual(len(self.launches), 1)
        launched, kw = self.launches[0]
        self.assertEqual(launched[0], str(self.pyw))
        self.assertEqual(launched[2], "service")
        self.assertEqual(kw["stdout"], subprocess.DEVNULL)
        self.assertFalse(self.store.paused)
        self.assertEqual(json.loads(auto.state_path(self.root).read_text())[
            "status"], "installed")
        self.assertFalse((self.root / "roadmap.json").exists())

    def test_reinstall_is_idempotent_and_keeps_user_queue(self):
        old = {"version": state.STATE_VERSION,
               "updated_at": state.utcnow(),
               "tasks": [{"id": "old-work", "status": "awaiting_review"}]}
        self.store.save(old)
        self.install()
        self.install()
        self.assertEqual(self.store.load()["tasks"], old["tasks"])
        self.assertEqual(len(self.launches), 2)
        self.assertEqual(len(self.calls), 2)

    def test_prevents_replacement_of_other_checkout(self):
        self.install()
        with self.assertRaisesRegex(ValueError, "different checkout"):
            auto.install(self.root, self.base / "other", runner=self.fake_runner,
                         popen=self.fake_popen, pythonexe=self.pyw,
                         appdata=self.app)

    def test_refuses_to_install_over_live_runner(self):
        with patch.object(auto, "runner_is_active", return_value=True):
            with self.assertRaisesRegex(ValueError, "currently running"):
                self.install()
        self.assertEqual(self.calls, [])

    def test_scheduler_failure_is_visible_and_does_not_launch(self):
        def rejected(args, **kwargs):
            return result(1)
        with self.assertRaisesRegex(RuntimeError, "Task Scheduler refused"):
            auto.install(self.root, self.checkout, runner=rejected,
                         popen=self.fake_popen, pythonexe=self.pyw,
                         appdata=self.app)
        self.assertEqual(self.launches, [])

    def test_checkout_refresh_rejects_dirty_and_never_resets(self):
        def dirty(args, **kw):
            return result(0, " M uncommitted.txt\n")
        with self.assertRaisesRegex(ValueError, "checkout has changes"):
            auto.refresh_checkout(self.checkout, runner=dirty)
        calls = []
        def fake(args, **kw):
            calls.append(args)
            if "fetch" in args:
                return result(1)
            if "rev-parse" in args:
                return result(0, "a" * 40)
            return result()
        self.assertEqual(auto.refresh_checkout(self.checkout, runner=fake),
                         "offline-existing-checkout")
        self.assertFalse(any("reset" in cmd for cmd in calls))
        self.assertFalse(any("clean" in cmd for cmd in calls))

    def test_single_owner_lock_rejects_competing_process(self):
        path = self.root / "locks" / "autopilot.lock"
        with auto.single_owner(path):
            with self.assertRaises(RuntimeError):
                with auto.single_owner(path):
                    pass
        with auto.single_owner(path):
            pass

    def test_service_defers_when_manual_supervisor_active(self):
        settings = self.install()
        with patch.object(auto, "runner_is_active", return_value=True):
            code = auto.execute_service(settings)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(auto.state_path(self.root).read_text())[
            "status"], "deferred")

    def test_service_honors_explicit_pause(self):
        settings = self.install()
        self.store.set_paused(True)
        self.assertEqual(auto.execute_service(settings), 0)
        self.assertEqual(json.loads(auto.state_path(self.root).read_text())[
            "status"], "paused")

    def test_service_checks_real_100_task_completion(self):
        settings = self.install()
        @contextmanager
        def no_conflict(*args):
            yield
        fake_supervisor = SimpleNamespace(
            run=lambda **kwargs: self.store.load(),
        )
        with patch.object(auto, "refresh_checkout", return_value="updated"), \
             patch.object(auto, "ensure_backlog"), \
             patch.object(auto, "get_queue_summary",
                          return_value={"awaiting_review": 100}), \
             patch("canopy_supervisor.cli.build_supervisor",
                   return_value=fake_supervisor):
            self.assertEqual(auto.execute_service(settings), 0)
        status = json.loads(auto.state_path(self.root).read_text())
        self.assertEqual(status["status"], "complete")
        self.assertEqual(status["counts"], {"awaiting_review": 100})

    def test_service_reports_incomplete_100_without_false_success(self):
        settings = self.install()
        fake_supervisor = SimpleNamespace(
            run=lambda **kwargs: self.store.load(),
        )
        with patch.object(auto, "refresh_checkout", return_value="updated"), \
             patch.object(auto, "ensure_backlog"), \
             patch.object(auto, "get_queue_summary",
                          return_value={"blocked": 2, "awaiting_review": 47}), \
             patch("canopy_supervisor.cli.build_supervisor",
                   return_value=fake_supervisor):
            self.assertEqual(auto.execute_service(settings), 2)
        status = json.loads(auto.state_path(self.root).read_text())
        self.assertEqual(status["status"], "incomplete")

    def test_uninstall_removes_only_owned_scheduler_entry(self):
        settings = self.install()
        self.calls.clear()
        auto.uninstall(settings, runner=self.fake_runner)
        self.assertFalse(settings.exists())
        self.assertEqual(self.calls[0][0][1], "/Delete")
        self.assertTrue(self.store.config_path.exists())
        self.assertEqual(json.loads(auto.state_path(self.root).read_text())[
            "status"], "uninstalled")

    def test_isolated_task_name_is_stable(self):
        self.assertEqual(auto.task_name(self.root), auto.task_name(self.root))
        self.assertNotEqual(auto.task_name(self.root),
                            auto.task_name(self.base / "another-root"))


if __name__ == "__main__":
    unittest.main()
