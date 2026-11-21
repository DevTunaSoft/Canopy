"""Host lifecycle tests with inert in-memory presenters (no QML execution)."""

import unittest

from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import ShellHost, SwitchBusy


class FakePresentation:
    def __init__(self, name, events, *, failures=None, check=None):
        self.name = name
        self.events = events
        self.failures = failures or {}
        self.check = check
        self.active = False

    def _call(self, method):
        self.events.append((self.name, method))
        callback = self.failures.get(method)
        if callable(callback):
            callback()
        elif callback:
            raise RuntimeError("secret-bearing dummy error should not leak")

    def prepare(self):
        self._call("prepare")

    def activate(self):
        if self.check is not None:
            self.check(self)
        self._call("activate")
        self.active = True

    def deactivate(self):
        self._call("deactivate")
        self.active = False

    def dispose(self):
        self._call("dispose")


class ShellHostTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.views = []
        self.created = {}
        records = []
        for name in ("classic", "modern", "minimal", "unauthorized", "requires-extra"):
            caps = frozenset(("dock", "workspace-list")) if name == "requires-extra" \
                else frozenset(("dock",))
            records.append(ShellPackInfo(
                pack_id="com.example." + name,
                name=name, description=name + " presentation",
                directory=__import__("pathlib").Path("/nonexecuted/" + name),
                entrypoint="ui/Main.qml", shell_api=1, ui_engine="qt-qml",
                capabilities=caps,
            ))
        self.catalog = PackScan(tuple(records), (), len(records))
        self.failures = {}
        self.callbacks = {}
        self.factories = {
            "com.example." + name: self.factory(name)
            for name in ("classic", "modern", "minimal", "requires-extra")
        }

    def factory(self, name):
        def create():
            self.events.append((name, "factory"))
            self.created[name] = self.created.get(name, 0) + 1
            view = FakePresentation(
                name, self.events, failures=self.failures.get(name, {}),
                check=self.callbacks.get(name)
            )
            self.views.append(view)
            return view
        return create

    def host(self, caps=None, factories=None):
        return ShellHost(
            self.catalog,
            self.factories if factories is None else factories,
            frozenset(("dock",)) if caps is None else caps,
        )

    @staticmethod
    def ident(name):
        return "com.example." + name

    def test_start_then_stop_with_full_cleanup(self):
        host = self.host()
        result = host.switch(self.ident("classic"))
        self.assertTrue(result.success)
        self.assertEqual(result.status, "SWITCHED")
        self.assertEqual(host.active_id, self.ident("classic"))
        result = host.stop()
        self.assertTrue(result.success)
        self.assertEqual(result.status, "STOPPED")
        self.assertIsNone(host.active_id)
        self.assertEqual(self.events[-2:], [("classic", "deactivate"), ("classic", "dispose")])

    def test_unlimited_presentations_three_distinct_switches(self):
        host = self.host()
        for name in ("classic", "modern", "minimal", "classic"):
            self.assertTrue(host.switch(self.ident(name)).success)
            self.assertEqual(host.active_id, self.ident(name))
        self.assertEqual(self.created, {"classic": 2, "modern": 1, "minimal": 1})
        self.assertEqual(sum(view.active for view in self.views), 1)

    def test_old_deactivated_before_new_activated(self):
        host = self.host()
        host.switch(self.ident("classic"))
        self.callbacks["modern"] = lambda view: self.assertEqual(
            sum(active.active for active in self.views), 0
        )
        result = host.switch(self.ident("modern"))
        self.assertTrue(result.success)
        self.assertLess(
            self.events.index(("classic", "deactivate")),
            self.events.index(("modern", "activate")),
        )
        self.assertEqual(sum(v.active for v in self.views), 1)

    def test_same_pack_is_noop_no_new_factory(self):
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("classic"))
        self.assertEqual(result.status, "ALREADY_ACTIVE")
        self.assertEqual(self.created, {"classic": 1})

    def test_unknown_untrusted_pack_never_executes_a_factory(self):
        host = self.host()
        result = host.switch(self.ident("unauthorized"))
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("explicitly trusted", result.note)
        self.assertEqual(self.events, [])

    def test_invalid_pack_not_in_catalog_rejected(self):
        host = self.host()
        self.assertEqual(host.switch("../../evil").status, "REJECTED")
        self.assertEqual(self.events, [])

    def test_missing_host_capability_rejected_before_factory(self):
        host = self.host()
        result = host.switch(self.ident("requires-extra"))
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(self.events, [])

    def test_supported_extra_capability_allows_trusted_factory(self):
        host = self.host(frozenset(("dock", "workspace-list")))
        self.assertTrue(host.switch(self.ident("requires-extra")).success)

    def test_constructor_rejects_noncallable_factory(self):
        with self.assertRaises(TypeError):
            self.host(factories={self.ident("classic"): "not a factory"})
        with self.assertRaises(TypeError):
            self.host(caps=["dock"])

    def test_prepare_failure_leaves_old_active(self):
        self.failures["modern"] = {"prepare": True}
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "PREPARE_FAILED")
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assertTrue(self.views[0].active)
        self.assertIn(("modern", "dispose"), self.events)
        self.assertNotIn(("classic", "deactivate"), self.events)

    def test_factory_failure_keeps_old_state(self):
        def bad_factory():
            raise RuntimeError("confidential exception detail")
        factories = {**self.factories, self.ident("modern"): bad_factory}
        host = self.host(factories=factories)
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "FACTORY_FAILED")
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assertNotIn("confidential", result.note)

    def test_activation_failure_rolls_back_old_view(self):
        self.failures["modern"] = {"activate": True}
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "ACTIVATE_FAILED")
        self.assertTrue(result.recovered)
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assertEqual(sum(view.active for view in self.views), 1)
        self.assertIn(("modern", "deactivate"), self.events)
        self.assertIn(("classic", "activate"), self.events)

    def test_activation_and_candidate_deactivation_failure_halts_recovery(self):
        self.failures["modern"] = {"activate": True, "deactivate": True}
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertTrue(host.needs_recovery)
        self.assertEqual(self.events.count(("classic", "activate")), 1)
        self.assertEqual(host.switch(self.ident("minimal")).status,
                         "RECOVERY_REQUIRED")

    def test_old_deactivation_failure_restores_or_aborts(self):
        self.failures["classic"] = {"deactivate": True}
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "DEACTIVATE_FAILED")
        self.assertTrue(result.recovered)
        self.assertEqual(host.active_id, self.ident("classic"))
        self.assertNotIn(("modern", "activate"), self.events)

    def test_old_restoration_failure_needs_manual_recovery(self):
        def fail_on_second_activate():
            if self.events.count(("classic", "activate")) > 1:
                raise RuntimeError("restoration failed")
        self.failures["modern"] = {"activate": True}
        self.failures["classic"] = {"activate": fail_on_second_activate}
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertTrue(host.needs_recovery)
        self.assertEqual(host.stop().status, "RECOVERY_REQUIRED")

    def test_cleanup_failure_is_visible_not_fake_success(self):
        self.failures["classic"] = {"dispose": True}
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.switch(self.ident("modern"))
        self.assertEqual(result.status, "CLEANUP_FAILED")
        self.assertFalse(result.success)
        self.assertEqual(host.active_id, self.ident("modern"))
        self.assertEqual(sum(view.active for view in self.views), 1)

    def test_stop_deactivation_failure_needs_recovery(self):
        self.failures["classic"] = {"deactivate": True}
        host = self.host()
        host.switch(self.ident("classic"))
        result = host.stop()
        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertTrue(host.needs_recovery)
        self.assertEqual(host.active_id, self.ident("classic"))

    def test_reentrant_callback_switch_is_blocked(self):
        host = self.host()
        def illegal_nested_switch():
            with self.assertRaises(SwitchBusy):
                host.switch(self.ident("modern"))
        self.failures["classic"] = {"prepare": illegal_nested_switch}
        result = host.switch(self.ident("classic"))
        self.assertTrue(result.success)
        self.assertEqual(self.created, {"classic": 1})

    def test_exception_notes_do_not_expose_secret_strings(self):
        self.failures["classic"] = {"prepare": True}
        host = self.host()
        result = host.switch(self.ident("classic"))
        self.assertNotIn("secret-bearing", result.note)
        self.assertEqual(result.status, "PREPARE_FAILED")

    def test_noop_stop_is_safe(self):
        host = self.host()
        self.assertEqual(host.stop().status, "STOPPED")
        self.assertIsNone(host.active_id)
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
