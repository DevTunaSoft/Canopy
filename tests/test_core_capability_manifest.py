"""Static capability-manifest audit: import-free, deterministic, fail-closed.

The audit reads catalog target source as text and parses it with ``ast``; it
must never import or execute a feature module. Bad entries become reported
problems, never escaped exceptions.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
import sys
import tempfile
import unittest

from canopy_core import capabilities
from canopy_core.capability_manifest import (
    EMPTY,
    INVALID,
    MISSING,
    NO_CALLABLE,
    UNREADABLE,
    UNSAFE,
    VISUAL,
    ManifestProblem,
    ManifestReport,
    verify,
)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class RealCatalogTests(unittest.TestCase):
    def test_real_catalog_audits_clean(self):
        report = verify()
        self.assertTrue(report.ok, report.problems)
        self.assertEqual(report.checked, len(capabilities.names()))
        self.assertEqual(report.problems, ())

    def test_audit_does_not_import_any_feature_module(self):
        targets = {capabilities.describe(name).module
                   for name in capabilities.names()}
        saved = {name: sys.modules[name]
                 for name in targets if name in sys.modules}
        for name in targets:
            sys.modules.pop(name, None)
        try:
            verify()
            leaked = sorted(name for name in targets if name in sys.modules)
            self.assertEqual(leaked, [])
        finally:
            for name in targets:
                sys.modules.pop(name, None)
            sys.modules.update(saved)

    def test_source_has_no_import_or_exec_paths(self):
        source = (Path(capabilities.__file__).parent
                  / "capability_manifest.py").read_text(encoding="utf-8")
        for forbidden in ("import_module", "__import__", "exec(", "eval("):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)

    def test_reports_are_immutable_and_ordered(self):
        report = verify()
        self.assertIsInstance(report, ManifestReport)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            report.checked = 0
        again = verify()
        self.assertEqual(report, again)


class SyntheticCatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        _write(self.root, "canopy_features/dummy/ok_mod.py",
               "def target():\n    return 1\n")

    def entries(self, **overrides):
        base = {"dummy.ok": ("canopy_features.dummy.ok_mod", "target", "dummy")}
        base.update(overrides)
        return base

    def test_valid_entry_passes(self):
        report = verify(entries=self.entries(), root=self.root)
        self.assertTrue(report.ok, report.problems)
        self.assertEqual(report.checked, 1)
        self.assertEqual(report.problems, ())

    def test_missing_module_is_reported_not_raised(self):
        report = verify(entries=self.entries(
            **{"dummy.bad": ("canopy_features.dummy.missing_mod",
                             "target", "dummy")}), root=self.root)
        self.assertFalse(report.ok)
        self.assertEqual(report.checked, 2)
        self.assertIn(("dummy.bad", MISSING),
                      [(p.name, p.reason) for p in report.problems])
        problem = report.problems[0]
        self.assertIsInstance(problem, ManifestProblem)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            problem.name = "x"

    def test_missing_callable_is_reported(self):
        report = verify(entries=self.entries(
            **{"dummy.bad": ("canopy_features.dummy.ok_mod",
                             "absent", "dummy")}), root=self.root)
        self.assertIn(("dummy.bad", NO_CALLABLE),
                      [(p.name, p.reason) for p in report.problems])

    def test_visual_target_is_rejected(self):
        _write(self.root, "canopy_features/dummy/visual_panel.py",
               "def target():\n    return 1\n")
        report = verify(entries=self.entries(
            **{"dummy.panel": ("canopy_features.dummy.visual_panel",
                               "target", "dummy")}), root=self.root)
        self.assertIn(("dummy.panel", VISUAL),
                      [(p.name, p.reason) for p in report.problems])

    def test_unreadable_source_is_reported_not_raised(self):
        _write(self.root, "canopy_features/dummy/broken_mod.py",
               "def target(:\n    pass\n")
        report = verify(entries=self.entries(
            **{"dummy.bad": ("canopy_features.dummy.broken_mod",
                             "target", "dummy")}), root=self.root)
        self.assertIn(("dummy.bad", UNREADABLE),
                      [(p.name, p.reason) for p in report.problems])

    def test_traversal_module_name_is_reported_without_path_access(self):
        probe = self.root / "canopy_features/dummy/evil_target.py"
        probe.write_text("def target():\n    return 1\n", encoding="utf-8")
        report = verify(entries=self.entries(
            **{"dummy.bad": ("canopy_features.dummy..evil_target",
                             "target", "dummy")}), root=self.root)
        self.assertIn(("dummy.bad", INVALID),
                      [(p.name, p.reason) for p in report.problems])
        # The malformed name must never be converted into a filesystem path.
        self.assertFalse((self.root / "canopy_features/dummy/..evil_target.py").exists())

    def test_symlinked_target_is_rejected(self):
        outside = self.root / "outside" / "outside_mod.py"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("def target():\n    return 1\n", encoding="utf-8")
        link = self.root / "canopy_features/dummy/linked_mod.py"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        report = verify(entries=self.entries(
            **{"dummy.bad": ("canopy_features.dummy.linked_mod",
                             "target", "dummy")}), root=self.root)
        self.assertIn(("dummy.bad", UNSAFE),
                      [(p.name, p.reason) for p in report.problems])

    def test_empty_catalog_is_a_problem(self):
        report = verify(entries={}, root=self.root)
        self.assertFalse(report.ok)
        self.assertEqual([(p.name, p.reason) for p in report.problems],
                         [("", EMPTY)])

    def test_problems_are_sorted_and_deterministic(self):
        _write(self.root, "canopy_features/dummy/aaa.py", "x = 1\n")
        entries = self.entries(
            **{"dummy.zzz": ("canopy_features.dummy.aaa", "target", "dummy"),
               "dummy.aaa": ("canopy_features.dummy.nope", "target", "dummy")})
        first = verify(entries=entries, root=self.root)
        second = verify(entries=entries, root=self.root)
        self.assertEqual(first, second)
        names = [p.name for p in first.problems]
        self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
