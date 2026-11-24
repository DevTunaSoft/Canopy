"""Fail-closed contract for hostile-but-bounded allowlists of environment names.

A caller-supplied allowlist is a validation boundary for build_environment: if
reading the names raises, no environment can be proven safe and the module's
domain error must be returned instead of a raw built-in exception. The fixtures
below are finite and offline; no process, socket, file or desktop is involved.
All values are synthetic markers, never real credentials.
"""
import unittest

from canopy_features.apps.environment_allowlist import (
    EnvironmentAllowlistError,
    build_environment,
)


class ExplodingNameIterable:
    """Finite allowlist that yields one name, then fails while being read."""

    def __init__(self, exc=None):
        self.exc = exc if exc is not None else OSError("allowlist source unavailable")
        self.consumed = 0

    def __iter__(self):
        yield "PATH"
        self.consumed += 1
        raise self.exc


class ExplodingNameIterator:
    """Finite iterator that raises on the read after a wrong-type name."""

    def __init__(self):
        self.consumed = 0

    def __iter__(self):
        return self

    def __next__(self):
        self.consumed += 1
        if self.consumed == 1:
            return "PATH"
        if self.consumed == 2:
            return 42  # wrong-type name
        raise RuntimeError("hostile iterator")


class HostileAllowlistNameTests(unittest.TestCase):
    SOURCE = {"PATH": "/usr/bin", "GITHUB_TOKEN": "SYNTHETIC_TOKEN_MARKER"}

    def test_allowlist_read_oserror_raises_domain_error(self):
        allowlist = ExplodingNameIterable()
        with self.assertRaises(EnvironmentAllowlistError):
            build_environment(allowlist, self.SOURCE)
        self.assertGreaterEqual(allowlist.consumed, 1)

    def test_allowlist_read_runtime_error_raises_domain_error(self):
        allowlist = ExplodingNameIterable(RuntimeError("boom"))
        with self.assertRaises(EnvironmentAllowlistError):
            build_environment(allowlist, self.SOURCE)
        self.assertGreaterEqual(allowlist.consumed, 1)

    def test_wrong_type_name_then_iteration_failure_raises_domain_error(self):
        allowlist = ExplodingNameIterator()
        with self.assertRaises(EnvironmentAllowlistError):
            build_environment(allowlist, self.SOURCE)
        self.assertGreaterEqual(allowlist.consumed, 2)

    def test_no_secret_marker_leaks_on_failed_allowlist_read(self):
        allowlist = ExplodingNameIterable(ValueError("hostile"))
        try:
            build_environment(allowlist, self.SOURCE)
        except EnvironmentAllowlistError as exc:
            self.assertNotIn("SYNTHETIC_TOKEN_MARKER", str(exc))
            self.assertNotIn("SYNTHETIC_TOKEN_MARKER", repr(exc))
        else:
            self.fail("hostile allowlist must be refused")

    def test_valid_finite_allowlist_still_copied(self):
        env = build_environment(("PATH", "MISSING"), self.SOURCE)
        self.assertEqual(env, {"PATH": "/usr/bin"})
        self.assertNotIn("SYNTHETIC_TOKEN_MARKER", repr(env))


if __name__ == "__main__":
    unittest.main()
