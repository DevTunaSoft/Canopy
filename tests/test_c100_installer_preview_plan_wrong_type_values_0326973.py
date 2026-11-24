"""Wrong-type path values must fail closed with the planner's domain error.

The planner is an offline dry-run gate: a hostile-but-bounded caller must never
get a raw built-in exception in place of ``PlanError``. These tests exercise
every public path-taking entry point and the private helper reached from them.
They are pure-offline and prove no Mint guest or compiled Qt behaviour.
"""
import os
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer import preview_install_plan as plan


class HostilePathLike:
    """A bounded caller object whose __fspath__ refuses to cooperate."""

    def __fspath__(self):
        raise TypeError("hostile fspath")


class WrongReturnPathLike:
    """A bounded caller object whose __fspath__ returns a non-path value."""

    def __fspath__(self):
        return 7


# ``None`` is the documented "use the caller default" sentinel for the
# optional data_home / allowed_root arguments, so it is deliberately absent:
# only hostile-but-bounded wrong-type *values* belong in this contract.
WRONG_PATHS = (7, True, [], {}, 1.5, b"/tmp/binary",
               HostilePathLike(), WrongReturnPathLike())


class WrongTypePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "canopy-classic-spike"
        self.binary.write_text("# placeholder\n", encoding="utf-8")
        self.binary.chmod(0o755)
        self.home = self.root / "xdg data home"
        self.art = self.root / "approved art"
        self.art.mkdir()
        self.result = plan.build_plan(self.binary, data_home=self.home,
                                      art=self.art)
        self.output = self.root / "plan.json"

    def assertDomainError(self, fn, label):
        with self.subTest(value=label), self.assertRaises(plan.PlanError):
            fn()

    def test_validate_qt_binary_wrong_types_fail_closed(self):
        for value in WRONG_PATHS:
            self.assertDomainError(
                lambda v=value: plan.validate_qt_binary(v),
                type(value).__name__)

    def test_build_plan_qt_binary_wrong_types_fail_closed(self):
        for value in WRONG_PATHS:
            self.assertDomainError(
                lambda v=value: plan.build_plan(v, data_home=self.home),
                type(value).__name__)

    def test_build_plan_data_home_wrong_types_fail_closed(self):
        for value in WRONG_PATHS:
            self.assertDomainError(
                lambda v=value: plan.build_plan(self.binary, data_home=v),
                type(value).__name__)

    def test_authorize_output_wrong_types_fail_closed(self):
        for value in WRONG_PATHS:
            self.assertDomainError(
                lambda v=value: plan.authorize_output(v, allowed_root=self.root),
                "output=" + type(value).__name__)
            self.assertDomainError(
                lambda v=value: plan.authorize_output(
                    self.output, allowed_root=v),
                "root=" + type(value).__name__)

    def test_write_plan_wrong_output_type_fail_closed(self):
        for value in WRONG_PATHS:
            self.assertDomainError(
                lambda v=value: plan.write_plan(
                    self.result, v, allowed_root=self.root),
                type(value).__name__)

    def test_valid_str_and_pathlike_still_accepted(self):
        """Coverage guard: the gate must not reject legitimate path inputs."""
        self.assertEqual(plan.validate_qt_binary(os.fspath(self.binary)),
                         str(self.binary))
        result = plan.build_plan(self.binary, data_home=os.fspath(self.home))
        self.assertEqual(result["data_home"], str(self.home))
        written = plan.write_plan(self.result, self.output,
                                  allowed_root=os.fspath(self.root))
        self.assertEqual(written, self.output)


if __name__ == "__main__":
    unittest.main()
