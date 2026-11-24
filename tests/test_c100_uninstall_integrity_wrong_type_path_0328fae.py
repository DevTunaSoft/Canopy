"""Hostile-but-bounded wrong-type path values must fail closed.

Public path-taking entry points of ``uninstall_integrity`` translated a
wrong-type path into a raw built-in ``TypeError`` from ``pathlib.Path`` instead
of the module's fail-closed contract. A hostile caller could therefore make the
planner crash, or observe a built-in exception where an integrity refusal is
required. No path outside a temporary tree is touched.

Values are a bounded, finite set of wrong-type scalars/containers; no infinite
or oversized iterable is used.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer.uninstall_integrity import (
    UninstallIntegrityError,
    UninstallPlan,
    plan_uninstall,
    plan_uninstall_file,
    read_manifest,
)


WRONG_PATH_VALUES = (None, 123, 1.5, [], {}, b"/tmp/install")


def digest(data):
    return hashlib.sha256(data).hexdigest()


class UninstallWrongTypePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="canopy-uii-wrongtype-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "install"
        self.root.mkdir()
        (self.root / "owned.txt").write_bytes(b"owned")
        self.manifest = {
            "schema": 1,
            "files": {"owned.txt": digest(b"owned")},
        }
        self.manifest_path = self.base / "ownership.json"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def assert_fails_closed(self, func, *args):
        """Accept only a domain refusal or a safe=False plan, never a raw error."""
        try:
            result = func(*args)
        except UninstallIntegrityError:
            return
        except Exception as exc:
            self.fail("raw %s escaped: %s" % (type(exc).__name__, exc))
        self.assertIsInstance(result, UninstallPlan)
        self.assertFalse(result.safe, "false integrity-safe claim: %r" % (result,))
        self.assertEqual(result.remove_files, ())

    def test_wrong_type_install_root_never_raises_raw_exception(self):
        for value in WRONG_PATH_VALUES:
            with self.subTest(value=repr(value)):
                self.assert_fails_closed(plan_uninstall, value, self.manifest)

    def test_wrong_type_manifest_path_never_raises_raw_exception(self):
        for value in WRONG_PATH_VALUES:
            with self.subTest(value=repr(value)):
                self.assert_fails_closed(read_manifest, value)

    def test_wrong_type_paths_in_convenience_wrapper_fail_closed(self):
        for value in WRONG_PATH_VALUES:
            with self.subTest(value=repr(value)):
                self.assert_fails_closed(
                    plan_uninstall_file, value, self.manifest_path)
                self.assert_fails_closed(
                    plan_uninstall_file, self.root, value)

    def test_valid_paths_still_produce_a_safe_plan(self):
        plan = plan_uninstall_file(self.root, self.manifest_path)
        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_files, ("owned.txt",))
        self.assertTrue((self.root / "owned.txt").is_file())


if __name__ == "__main__":
    unittest.main()
