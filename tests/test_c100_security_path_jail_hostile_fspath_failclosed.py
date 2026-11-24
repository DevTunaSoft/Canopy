"""Regression tests: hostile ``__fspath__``/``__repr__`` hostiles must fail
closed with the module's domain error, never leak a raw built-in exception.

PR #466 hardened Unicode case folding; PR #476 later gated wrong-typed
arguments that ``os.fspath`` rejects with ``TypeError``. Neither path covers a
hostile ``os.PathLike`` whose ``__fspath__`` raises a *different* exception
(RuntimeError, ValueError, ...), nor an object whose ``__repr__`` raises while
the domain error is being formatted. Callers that catch only ``PathJailError``
cannot contain either leak.

Pure/offline tests plus one bounded temporary directory; no Qt, network,
privileged operations, symlinks or unbounded iterables.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.security import path_jail_checks as jail  # noqa: E402


class HostileFspath:
    """A PathLike whose __fspath__ raises a non-TypeError exception."""

    def __init__(self, exc_type):
        self._exc_type = exc_type

    def __fspath__(self):
        raise self._exc_type("hostile __fspath__")


class HostileRepr:
    """A PathLike whose __repr__ raises while the error is formatted."""

    def __init__(self, raw):
        self._raw = raw

    def __fspath__(self):
        return self._raw

    def __repr__(self):
        raise RuntimeError("hostile __repr__")


class HostileReprNoFspath:
    """Not a PathLike at all, and repr() itself explodes."""

    def __repr__(self):
        raise RuntimeError("hostile __repr__ without __fspath__")


class FailClosedTestCase(unittest.TestCase):
    """Turn a leaked built-in exception into a readable test FAIL."""

    def assert_path_jail_error(self, call):
        try:
            call()
        except jail.PathJailError:
            return
        except BaseException as exc:
            self.fail(
                f"leaked {type(exc).__name__} instead of PathJailError: {exc}"
            )
        self.fail("hostile path argument was accepted without a domain error")


class HostileFspathTests(FailClosedTestCase):
    EXC_TYPES = (RuntimeError, ValueError, OSError)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "jail"
        self.root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_canonicalize_hostile_fspath_is_domain_error(self):
        for exc_type in self.EXC_TYPES:
            with self.subTest(exc_type=exc_type.__name__):
                self.assert_path_jail_error(
                    lambda e=exc_type: jail.canonicalize(HostileFspath(e))
                )

    def test_resolve_within_hostile_fspath_candidate_is_domain_error(self):
        for exc_type in self.EXC_TYPES:
            with self.subTest(exc_type=exc_type.__name__):
                self.assert_path_jail_error(
                    lambda e=exc_type: jail.resolve_within(
                        self.root, HostileFspath(e))
                )

    def test_resolve_within_hostile_fspath_root_is_domain_error(self):
        self.assert_path_jail_error(
            lambda: jail.resolve_within(HostileFspath(RuntimeError), "x")
        )

    def test_is_contained_hostile_fspath_is_domain_error(self):
        for exc_type in self.EXC_TYPES:
            with self.subTest(exc_type=exc_type.__name__):
                self.assert_path_jail_error(
                    lambda e=exc_type: jail.is_contained(
                        HostileFspath(e), self.root, case_sensitive=True)
                )
        self.assert_path_jail_error(
            lambda: jail.is_contained(
                self.root, HostileFspath(ValueError), case_sensitive=True)
        )

    def test_valid_pathlike_still_resolves(self):
        # Guard against over-correction: well-behaved PathLike inputs work.
        class GoodPathLike:
            def __init__(self, value):
                self._value = value

            def __fspath__(self):
                return self._value

        good = GoodPathLike(str(self.root))
        self.assertEqual(jail.canonicalize(good), self.root.resolve())
        self.assertEqual(jail.resolve_within(good, "sub"),
                         (self.root / "sub").resolve())


class HostileReprTests(FailClosedTestCase):
    ROOT = Path("/home/alice")

    def test_non_fspath_with_hostile_repr_is_domain_error(self):
        self.assert_path_jail_error(
            lambda: jail.canonicalize(HostileReprNoFspath())
        )

    def test_bytes_with_hostile_repr_is_domain_error(self):
        self.assert_path_jail_error(
            lambda: jail.canonicalize(HostileRepr(b"/tmp"))
        )

    def test_hostile_repr_in_is_contained_is_domain_error(self):
        # A str-returning PathLike is valid input and never formats an error;
        # use the bytes branch so the hostile repr is actually exercised.
        self.assert_path_jail_error(
            lambda: jail.is_contained(
                HostileRepr(b"/home/alice"), self.ROOT, case_sensitive=True)
        )


if __name__ == "__main__":
    unittest.main()
