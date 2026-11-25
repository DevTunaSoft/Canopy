"""Trusted Shell Host fault injection: lifecycle, cleanup and recovery invariants.

All adapters are inert in-memory objects created by host-registered factories.
No Shell Pack metadata path, QML file, archive or plugin is imported or loaded.
"""

import threading
import unittest
from pathlib import Path

from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import ShellHost, SwitchBusy


class SecretBearingFailure(Exception):
    pass


class FaultView:
    def __init__(self, name, log, failures):
        self.name = name
        self.log = log
        self.failures = failures
        self.active = False
        self.calls = {"prepare": 0, "activate": 0, "deactivate": 0, "dispose": 0}

    def _invoke(self, method):
        self.log.append((self.name, method))
        self.calls[method] += 1
        failure = self.failures.get(method)
        if failure:
            if callable(failure):
                failure()
            else:
                raise RuntimeError("secret token SUPERSECRET-42 must not leak")

    def prepare(self):
        self._invoke("prepare")

    def activate(self):
        self._invoke("activate")
        self.active = True

    def deactivate(self):
        self._invoke("deactivate")
        self.active = False

    def dispose(self):
        self._invoke("dispose")


class ShellHostFaultMatrixTests(unittest.TestCase):
    NAMES = ("classic", "modern", "minimal", "untrusted", "extra-cap")

    def setUp(self):
        self.fresh()

    def fresh(self):
        self.log = []
        self.views = []
        self.factory_calls = {name: 0 for name in self.NAMES}
        self.failures = {name: {} for name in self.NAMES}
        records = []
        for name in self.NAMES:
            caps = frozenset(("dock", "workspace-list")) if name == "extra-cap" \
                else frozenset(("dock",))
            records.append(ShellPackInfo(
                pack_id=self.ident(name),
                name=name,
                description=name + " presentation",
                directory=Path("/nonexecuted") / name,
                entrypoint="ui/Main.qml",
                shell_api=1,
                ui_engine="qt-qml",
                capabilities=caps,
            ))
        self.catalog = PackScan(tuple(records), (), len(records))
        self.factories = {self.ident(name): self.factory(name) for name in self.NAMES
                          if name not in ("untrusted",)}

    @staticmethod
    def ident(name):
        return "com.example." + name

    def factory(self, name):
        def create():
            self.factory_calls[name] += 1
            self.log.append((name, "factory"))
            view = FaultView(name, self.log, self.failures[name])
            self.views.append(view)
            return view
        return create

    def make_host(self, factories=None, capabilities=None):
        return ShellHost(
            self.catalog,
            self.factories if factories is None else factories,
            frozenset(("dock",)) if capabilities is None else capabilities,
        )

    def active_views(self):
        return [view for view in self.views if view.active]

    def assert_state_invariant(self, host, expected_active=None):
        active = self.active_views()
        self.assertLessEqual(len(active), 1)
        if not host.needs_recovery:
            if host.active_id is None:
                self.assertEqual(active, [])
            else:
                self.assertEqual(len(active), 1)
                self.assertEqual(active[0].name,
                                 host.active_id.removeprefix("com.example."))
        if expected_active is not None:
            self.assertEqual(host.active_id, self.ident(expected_active))
            self.assertEqual([v.name for v in active], [expected_active])
        for view in self.views:
            self.assertLessEqual(view.calls["dispose"], 1)

    def assert_freeze(self, host):
        before_events = list(self.log)
        before_views = len(self.views)
        before_calls = dict(self.factory_calls)
        self.assertEqual(host.switch(self.ident("minimal")).status,
                         "RECOVERY_REQUIRED")
        self.assertEqual(host.stop().status, "RECOVERY_REQUIRED")
        self.assertEqual(self.log, before_events)
        self.assertEqual(len(self.views), before_views)
        self.assertEqual(self.factory_calls, before_calls)

    def test_factory_returning_none_is_failure_not_crash(self):
        def none_factory():
            self.factory_calls["modern"] += 1
            return None

        factories = dict(self.factories)
        factories[self.ident("modern")] = none_factory
        host = self.make_host(factories=factories)
        self.assertTrue(host.switch(self.ident("classic")).success)
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "FACTORY_FAILED")
        self.assertEqual(result.active_id, self.ident("classic"))
        self.assertEqual(self.factory_calls["modern"], 1)
        self.assertEqual([v.name for v in self.views], ["classic"])
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assert_state_invariant(host, "classic")
        self.assertFalse(host.needs_recovery)
        self.assertTrue(host.switch(self.ident("minimal")).success)

    def test_exception_type_recorded_and_secret_message_never_leaked(self):
        def secret_factory():
            raise SecretBearingFailure("token SUPERSECRET-42 in message")
        factories = dict(self.factories)
        factories[self.ident("modern")] = secret_factory
        host = self.make_host(factories=factories)
        host.switch(self.ident("classic"))
        factory_result = host.switch(self.ident("modern"))
        self.assertEqual(factory_result.status, "FACTORY_FAILED")
        self.assertEqual(factory_result.note, "SecretBearingFailure")
        self.assertNotIn("SUPERSECRET", factory_result.note)

        self.failures["minimal"]["prepare"] = secret_factory
        prepare_result = host.switch(self.ident("minimal"))
        self.assertEqual(prepare_result.status, "PREPARE_FAILED")
        self.assertEqual(prepare_result.note, "prepare: SecretBearingFailure")
        self.assertNotIn("SUPERSECRET", prepare_result.note)
        self.assert_state_invariant(host, "classic")
        self.assertFalse(host.needs_recovery)

    def test_prepare_failure_without_old_view_cleans_candidate_and_stays_usable(self):
        self.failures["classic"]["prepare"] = True
        host = self.make_host()
        result = host.switch(self.ident("classic"))
        self.assertEqual(result.status, "PREPARE_FAILED")
        self.assertFalse(result.recovered)
        self.assertIsNone(host.active_id)
        self.assertEqual(len(self.views), 1)
        self.assertEqual(self.views[0].calls["dispose"], 1)
        self.assertEqual(self.active_views(), [])
        self.assert_state_invariant(host)
        self.assertFalse(host.needs_recovery)
        self.assertTrue(host.switch(self.ident("modern")).success)
        self.assert_state_invariant(host, "modern")

    def test_activation_failure_order_disposes_candidate_before_restoring_old(self):
        self.failures["modern"]["activate"] = True
        host = self.make_host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "ACTIVATE_FAILED")
        self.assertEqual(
            self.log[-4:],
            [("modern", "activate"), ("modern", "deactivate"),
             ("modern", "dispose"), ("classic", "activate")],
        )
        self.assertEqual(self.views[1].calls["dispose"], 1)
        self.assertEqual(self.views[0].calls["dispose"], 0)
        self.assert_state_invariant(host, "classic")

    def test_deactivation_failure_disposes_candidate_and_reactivates_old(self):
        self.failures["classic"]["deactivate"] = True
        host = self.make_host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "DEACTIVATE_FAILED")
        self.assertTrue(result.recovered)
        self.assertEqual(self.log[-3:],
                         [("classic", "deactivate"), ("modern", "dispose"),
                          ("classic", "activate")])
        self.assertNotIn(("modern", "activate"), self.log)
        self.assertEqual(self.views[1].calls["dispose"], 1)
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assert_state_invariant(host, "classic")

    def test_repeated_prepare_failures_do_not_leak_candidate_views(self):
        self.failures["modern"]["prepare"] = True
        host = self.make_host()
        self.assertTrue(host.switch(self.ident("classic")).success)
        for _ in range(25):
            result = host.switch(self.ident("modern"))
            self.assertEqual(result.status, "PREPARE_FAILED")
            self.assert_state_invariant(host, "classic")
        self.assertEqual(len(self.views), 26)
        for view in self.views[1:]:
            self.assertEqual(view.calls["dispose"], 1)
        self.assertEqual(self.views[0].calls["dispose"], 0)
        self.assertFalse(host.needs_recovery)
        self.assertTrue(host.switch(self.ident("minimal")).success)

    def test_repeated_switching_round_trips_dispose_each_retired_view_once(self):
        host = self.make_host()
        targets = ["classic", "modern"] * 30
        for name in targets:
            result = host.switch(self.ident(name))
            self.assertEqual(result.status, "SWITCHED")
            self.assert_state_invariant(host, name)
        self.assertEqual(len(self.views), len(targets))
        for view in self.views[:-1]:
            self.assertEqual(view.calls["dispose"], 1)
        self.assertEqual(self.views[-1].calls["dispose"], 0)
        self.assertEqual(host.active_id, self.ident(targets[-1]))
        result = host.stop()
        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(self.views[-1].calls["dispose"], 1)
        self.assertEqual(self.active_views(), [])
        self.assertIsNone(host.active_id)
        self.assert_state_invariant(host)

    def test_switch_uses_metadata_and_trusted_factory_without_touching_qml_paths(self):
        records = list(self.catalog.packs)
        unreachable = ShellPackInfo(
            pack_id=self.ident("offline"),
            name="offline",
            description="pack whose QML path does not exist",
            directory=Path("/definitely/not/executed/offline"),
            entrypoint="ui/Missing.qml",
            shell_api=1,
            ui_engine="qt-qml",
            capabilities=frozenset(("dock",)),
        )
        self.catalog = PackScan(tuple(records) + (unreachable,), (), len(records) + 1)
        self.factory_calls["offline"] = 0
        self.factories[self.ident("offline")] = self.factory("offline")
        self.failures["offline"] = {}
        host = self.make_host()
        result = host.switch(self.ident("offline"))
        self.assertEqual(result.status, "SWITCHED")
        self.assertEqual(self.factory_calls["offline"], 1)
        self.assert_state_invariant(host, "offline")

    def test_switch_busy_from_other_thread_while_transition_locked(self):
        host = self.make_host()
        self.assertTrue(host.switch(self.ident("classic")).success)
        outcomes = []

        def worker():
            for action in ("switch", "stop"):
                try:
                    if action == "switch":
                        host.switch(self.ident("modern"))
                    else:
                        host.stop()
                    outcomes.append((action, "NO_ERROR"))
                except SwitchBusy:
                    outcomes.append((action, "SwitchBusy"))

        host._lock.acquire()
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5)
        host._lock.release()
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes,
                         [("switch", "SwitchBusy"), ("stop", "SwitchBusy")])
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assert_state_invariant(host, "classic")

    def test_deterministic_single_fault_matrix(self):
        scenarios = [
            ("prepare", "switch", "modern", {"modern": {"prepare": True}},
             "PREPARE_FAILED", False, "classic"),
            ("prepare_cleanup", "switch", "modern",
             {"modern": {"prepare": True, "dispose": True}},
             "RECOVERY_REQUIRED", True, "classic"),
            ("activate", "switch", "modern", {"modern": {"activate": True}},
             "ACTIVATE_FAILED", False, "classic"),
            ("activate_candidate_off", "switch", "modern",
             {"modern": {"activate": True, "deactivate": True}},
             "RECOVERY_REQUIRED", True, "classic"),
            ("activate_candidate_cleanup", "switch", "modern",
             {"modern": {"activate": True, "dispose": True}},
             "RECOVERY_REQUIRED", True, "classic"),
            ("old_deactivate", "switch", "modern", {"classic": {"deactivate": True}},
             "DEACTIVATE_FAILED", False, "classic"),
            ("old_deactivate_candidate_cleanup", "switch", "modern",
             {"classic": {"deactivate": True}, "modern": {"dispose": True}},
             "RECOVERY_REQUIRED", True, "classic"),
            ("cleanup", "switch", "modern", {"classic": {"dispose": True}},
             "CLEANUP_FAILED", True, "modern"),
            ("stop_deactivate", "stop", None, {"classic": {"deactivate": True}},
             "RECOVERY_REQUIRED", True, "classic"),
            ("stop_cleanup", "stop", None, {"classic": {"dispose": True}},
             "CLEANUP_FAILED", True, None),
        ]
        for label, action, target, failures, status, recovery, expected in scenarios:
            with self.subTest(label=label):
                self.fresh()
                host = self.make_host()
                self.assertTrue(host.switch(self.ident("classic")).success)
                for name, methods in failures.items():
                    self.failures[name].update(methods)
                if action == "switch":
                    result = host.switch(self.ident(target))
                    self.assertEqual(result.from_id, self.ident("classic"))
                    self.assertEqual(result.to_id, self.ident(target))
                else:
                    result = host.stop()
                    self.assertEqual(result.from_id, self.ident("classic"))
                    self.assertIsNone(result.to_id)
                self.assertEqual(result.status, status)
                self.assertEqual(host.needs_recovery, recovery)
                self.assertEqual(result.recovered, not recovery)
                if recovery:
                    self.assertFalse(result.success)
                    self.assert_freeze(host)
                else:
                    self.assertTrue(result.recovered)
                    self.assert_state_invariant(host, expected)
                    for methods in self.failures.values():
                        methods.clear()
                    self.assertTrue(host.switch(self.ident("minimal")).success)
                    self.assert_state_invariant(host, "minimal")

    def test_old_restoration_failure_freezes_even_after_partial_rollback(self):
        state = {"restore_calls": 0}

        def fail_restore():
            state["restore_calls"] += 1
            raise RuntimeError("restore failed")

        host = self.make_host()
        self.assertTrue(host.switch(self.ident("classic")).success)
        self.failures["modern"]["activate"] = True
        self.failures["classic"]["activate"] = fail_restore
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertTrue(host.needs_recovery)
        self.assertEqual(state["restore_calls"], 1)
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assert_freeze(host)


    def test_constructor_validates_trusted_inputs(self):
        with self.assertRaises(TypeError):
            ShellHost(self.catalog, self.factories, set(("dock",)))
        with self.assertRaises(TypeError):
            ShellHost("not a PackScan", self.factories, frozenset(("dock",)))
        with self.assertRaises(TypeError):
            ShellHost(self.catalog, {self.ident("modern"): object()},
                      frozenset(("dock",)))
        with self.assertRaises(TypeError):
            ShellHost(self.catalog, {123: lambda: None}, frozenset(("dock",)))
        self.assertEqual(self.views, [])

    def test_rejects_untrusted_unknown_capability_and_invalid_id_without_loading(self):
        host = self.make_host()
        cases = (
            (self.ident("untrusted"), "no explicitly trusted host adapter registered"),
            (self.ident("ghost"), "pack ID not in validated metadata catalog"),
            (self.ident("extra-cap"), "capability requirements unsupported"),
            (None, "invalid pack ID"),
        )
        for target, note in cases:
            with self.subTest(target=target):
                result = host.switch(target)
                self.assertEqual(result.status, "REJECTED")
                self.assertEqual(result.note, note)
        self.assertEqual(self.views, [])
        self.assertEqual(sum(self.factory_calls.values()), 0)
        self.assertIsNone(host.active_id)
        self.assertFalse(host.needs_recovery)
        self.assert_state_invariant(host)

    def test_already_active_returns_without_factory_or_lifecycle_calls(self):
        host = self.make_host()
        self.assertTrue(host.switch(self.ident("classic")).success)
        calls_after_first = dict(self.factory_calls)
        log_after_first = list(self.log)
        result = host.switch(self.ident("classic"))
        self.assertEqual(result.status, "ALREADY_ACTIVE")
        self.assertTrue(result.success)
        self.assertTrue(result.recovered)
        self.assertEqual(result.active_id, self.ident("classic"))
        self.assertEqual(self.factory_calls, calls_after_first)
        self.assertEqual(self.log, log_after_first)
        self.assertEqual(len(self.views), 1)
        self.assert_state_invariant(host, "classic")

    def test_factory_reusing_active_instance_is_failure(self):
        holder = {}

        def modern_factory():
            return holder.get("view")

        factories = dict(self.factories)
        factories[self.ident("modern")] = modern_factory
        host = self.make_host(factories=factories)
        self.assertTrue(host.switch(self.ident("classic")).success)
        holder["view"] = self.views[0]
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "FACTORY_FAILED")
        self.assertEqual(result.note, "trusted adapter factory reused the active instance")
        self.assertTrue(result.recovered)
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assertEqual(len(self.views), 1)
        self.assertEqual(self.active_views(), [self.views[0]])
        self.assertFalse(host.needs_recovery)
        self.assert_state_invariant(host, "classic")

    def test_stop_without_active_view_and_restart(self):
        host = self.make_host()
        result = host.stop()
        self.assertEqual(result.status, "STOPPED")
        self.assertTrue(result.success)
        self.assertIsNone(result.active_id)
        self.assertFalse(host.needs_recovery)
        self.assertEqual(self.views, [])
        self.assertTrue(host.switch(self.ident("classic")).success)
        self.assert_state_invariant(host, "classic")
        result = host.stop()
        self.assertEqual(result.status, "STOPPED")
        self.assertEqual(self.views[0].calls["dispose"], 1)
        self.assertEqual(self.active_views(), [])
        self.assertIsNone(host.active_id)
        self.assert_state_invariant(host)

    def test_factory_failure_with_no_active_view_stays_usable(self):
        def none_factory():
            self.factory_calls["modern"] += 1
            return None

        factories = dict(self.factories)
        factories[self.ident("modern")] = none_factory
        host = self.make_host(factories=factories)
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "FACTORY_FAILED")
        self.assertFalse(result.recovered)
        self.assertIsNone(result.active_id)
        self.assertEqual(self.factory_calls["modern"], 1)
        self.assertEqual(self.views, [])
        self.assertFalse(host.needs_recovery)
        self.assert_state_invariant(host)
        self.assertTrue(host.switch(self.ident("classic")).success)
        self.assert_state_invariant(host, "classic")

    def secret_failure(self):
        raise SecretBearingFailure("token SUPERSECRET-42 in message")

    def test_all_fault_notes_never_leak_secret_messages(self):
        def secret_factory():
            raise SecretBearingFailure("token SUPERSECRET-42 in message")

        factories = dict(self.factories)
        factories[self.ident("modern")] = secret_factory
        host = self.make_host(factories=factories)
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "FACTORY_FAILED")
        self.assertTrue(result.note)
        self.assertNotIn("SUPERSECRET", result.note)

        scenarios = [
            ("prepare", {"modern": {"prepare": self.secret_failure}},
             "PREPARE_FAILED", "switch", "modern"),
            ("old_deactivate", {"classic": {"deactivate": self.secret_failure}},
             "DEACTIVATE_FAILED", "switch", "modern"),
            ("candidate_activate", {"modern": {"activate": self.secret_failure}},
             "ACTIVATE_FAILED", "switch", "modern"),
            ("candidate_off", {"modern": {"activate": True,
                                          "deactivate": self.secret_failure}},
             "RECOVERY_REQUIRED", "switch", "modern"),
            ("prepare_cleanup", {"modern": {"prepare": True,
                                            "dispose": self.secret_failure}},
             "RECOVERY_REQUIRED", "switch", "modern"),
            ("old_restore", {"modern": {"activate": True},
                             "classic": {"activate": self.secret_failure}},
             "RECOVERY_REQUIRED", "switch", "modern"),
            ("old_cleanup", {"classic": {"dispose": self.secret_failure}},
             "CLEANUP_FAILED", "switch", "modern"),
            ("stop_deactivate", {"classic": {"deactivate": self.secret_failure}},
             "RECOVERY_REQUIRED", "stop", None),
            ("stop_dispose", {"classic": {"dispose": self.secret_failure}},
             "CLEANUP_FAILED", "stop", None),
        ]
        for label, failures, status, action, target in scenarios:
            with self.subTest(label=label):
                self.fresh()
                host = self.make_host()
                self.assertTrue(host.switch(self.ident("classic")).success)
                for name, methods in failures.items():
                    self.failures[name].update(methods)
                if action == "switch":
                    result = host.switch(self.ident(target))
                else:
                    result = host.stop()
                self.assertEqual(result.status, status)
                self.assertTrue(result.note)
                self.assertNotIn("SUPERSECRET", result.note)

    def test_repeated_activation_failures_do_not_leak_candidate_views(self):
        self.failures["modern"]["activate"] = True
        host = self.make_host()
        self.assertTrue(host.switch(self.ident("classic")).success)
        for _ in range(25):
            result = host.switch(self.ident("modern"))
            self.assertEqual(result.status, "ACTIVATE_FAILED")
            self.assertTrue(result.recovered)
            self.assert_state_invariant(host, "classic")
        self.assertEqual(len(self.views), 26)
        for view in self.views[1:]:
            self.assertEqual(view.calls["dispose"], 1)
        self.assertEqual(self.views[0].calls["dispose"], 0)
        self.assertFalse(host.needs_recovery)
        self.failures["modern"].clear()
        self.assertTrue(host.switch(self.ident("minimal")).success)
        self.assert_state_invariant(host, "minimal")

    def test_repeated_deactivation_failures_keep_old_view_and_stay_usable(self):
        self.failures["classic"]["deactivate"] = True
        host = self.make_host()
        self.assertTrue(host.switch(self.ident("classic")).success)
        for _ in range(25):
            result = host.switch(self.ident("modern"))
            self.assertEqual(result.status, "DEACTIVATE_FAILED")
            self.assertTrue(result.recovered)
            self.assertEqual(host.active_id, self.ident("classic"))
            self.assertEqual([v.name for v in self.active_views()], ["classic"])
        self.assertEqual(len(self.views), 26)
        for view in self.views[1:]:
            self.assertEqual(view.calls["dispose"], 1)
        self.assertEqual(self.views[0].calls["dispose"], 0)
        self.assertFalse(host.needs_recovery)
        self.failures["classic"].clear()
        self.assertTrue(host.switch(self.ident("minimal")).success)
        self.assert_state_invariant(host, "minimal")

    def test_recovery_freeze_blocks_every_later_switch_and_stop(self):
        self.failures["classic"]["prepare"] = True
        self.failures["classic"]["dispose"] = True
        host = self.make_host()
        result = host.switch(self.ident("classic"))
        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertTrue(host.needs_recovery)
        for _ in range(5):
            self.assert_freeze(host)
        self.assertIsNone(host.active_id)


if __name__ == "__main__":
    unittest.main()
