"""Shell Host exposes only host-allowed, static, nonvisual capabilities."""
from __future__ import annotations

import unittest
from pathlib import Path

from canopy_core.capabilities import CapabilityError, names as catalog_names
from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import ShellHost


def scan():
    pack = ShellPackInfo(
        pack_id="com.example.classic", name="classic", description="test pack",
        directory=Path("/nonexecuted/classic"), entrypoint="ui/Main.qml",
        shell_api=1, ui_engine="qt-qml", capabilities=frozenset({"dock"}))
    return PackScan((pack,), (), 1)


class ShellHostCapabilityTests(unittest.TestCase):
    def host(self, capabilities):
        return ShellHost(scan(), {}, frozenset(capabilities))

    def test_available_capabilities_are_host_gated_and_sorted(self):
        chosen = ("dock.pins.state", "accessibility.contrast.ratio")
        host = self.host(set(chosen) | {"dock"})
        self.assertEqual(host.available_capabilities(), tuple(sorted(chosen)))

    def test_empty_allowlist_exposes_nothing(self):
        self.assertEqual(self.host({"dock"}).available_capabilities(), ())

    def test_results_never_exceed_the_static_catalog(self):
        host = self.host(set(catalog_names()))
        self.assertTrue(set(host.available_capabilities()).issubset(set(catalog_names())))

    def test_describe_allowed_capability(self):
        descriptor = self.host({"dock.pins.state"}).describe_capability("dock.pins.state")
        self.assertEqual(descriptor.name, "dock.pins.state")
        self.assertEqual(descriptor.area, "dock")
        self.assertFalse(descriptor.visual)

    def test_unknown_or_unallowed_describe_is_rejected(self):
        host = self.host({"dock.pins.state"})
        for name in ("dock.running.state", "not.a.capability", None, 7):
            with self.subTest(name=name), self.assertRaises(CapabilityError):
                host.describe_capability(name)  # type: ignore[arg-type]

    def test_load_returns_callable_only_for_allowed_capability(self):
        host = self.host({"accessibility.contrast.ratio"})
        self.assertTrue(callable(host.load_capability("accessibility.contrast.ratio")))
        with self.assertRaises(CapabilityError):
            host.load_capability("dock.pins.state")

    def test_query_does_not_change_lifecycle_state(self):
        host = self.host({"dock.pins.state"})
        before = (host.active_id, host.needs_recovery)
        host.available_capabilities()
        host.describe_capability("dock.pins.state")
        self.assertEqual((host.active_id, host.needs_recovery), before)


if __name__ == "__main__":
    unittest.main()
