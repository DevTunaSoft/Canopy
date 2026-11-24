"""Regression tests: wrong-typed path arguments must fail closed with PathJailError.

PR #466 hardened canonicalization against casefold widening but left a
deferred contract: a ``bytes`` path reaching :func:`canonicalize`, or a
wrong-typed candidate/root reaching :func:`resolve_within` /
:func:`is_contained`, escapes as a raw built-in ``TypeError`` from ``Path()``.
Callers that catch the module's domain error cannot contain that leak.

Pure/offline tests (one bounded temporary directory); no Qt, network,
privileged operations or unbounded iterables.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.security import path_jail_checks as jail  # noqa: E402


class DomainErrorTestCase(unittest.TestCase):
    """Turn a leaked built-in exception into a readable test FAIL."""

    def assert_path_jail_error(self, call):
        try:
            call()
        except jail.PathJailError:
            return
        except TypeError as exc:
            self.fail(f"raw TypeError leaked instead of PathJailError: {exc!r}")
        except Exception as exc:  # noqa: BLE001 - any other leak is a failure
            self.fail(f"unexpected {type(exc).__name__} instead of PathJailError: {exc!r}")
        self.fail("wrong-typed path was accepted without a domain error")


class CanonicalizeWrongTypeTests(DomainErrorTestCase):
    def test_bytes_absolute_path_is_domain_error(self):
        self.assert_path_jail_error(lambda: jail.canonicalize(b"/tmp"))

    def test_bytes_relative_path_is_domain_error(self):
        self.assert_path_jail_error(lambda: jail.canonicalize(b"./relative"))

    def test_non_fspath_types_stay_domain_errors(self):
        # Control: these were already gated by os.fspath in the base contract.
        for value in (bytearray(b"/tmp"), 123):
            with self.subTest(value=value):
                self.assert_path_jail_error(lambda v=value: jail.canonicalize(v))


class ResolveWithinWrongTypeTests(DomainErrorTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "jail"
        self.root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_bytes_candidate_is_domain_error(self):
        self.assert_path_jail_error(
            lambda: jail.resolve_within(str(self.root), b"sub"))

    def test_scalar_and_container_candidates_are_domain_errors(self):
        for candidate in (123, ["sub"], {"a": 1}, 3.5, object()):
            with self.subTest(candidate=type(candidate).__name__):
                self.assert_path_jail_error(
                    lambda c=candidate: jail.resolve_within(str(self.root), c))

    def test_bytes_root_is_domain_error(self):
        self.assert_path_jail_error(lambda: jail.resolve_within(b"/tmp", "x"))

    def test_valid_str_and_path_inputs_still_resolve(self):
        # Guard against over-correction of the new type gates.
        self.assertEqual(jail.resolve_within(self.root, "sub"),
                         (self.root / "sub").resolve())
        self.assertEqual(jail.resolve_within(self.root, self.root / "sub"),
                         (self.root / "sub").resolve())


class IsContainedWrongTypeTests(DomainErrorTestCase):
    ROOT = Path("/home/alice")

    def test_wrong_candidate_types_are_domain_errors(self):
        for candidate in (b"/home/alice/sub", 123, ["a"], {"a": 1}, None, object()):
            with self.subTest(candidate=type(candidate).__name__):
                self.assert_path_jail_error(
                    lambda c=candidate: jail.is_contained(c, self.ROOT))

    def test_wrong_root_types_are_domain_errors(self):
        for root in (b"/home/alice", None):
            with self.subTest(root=type(root).__name__):
                self.assert_path_jail_error(
                    lambda r=root: jail.is_contained(self.ROOT, r))

    def test_valid_string_inputs_still_compare(self):
        # Guard against over-correction: str inputs remain accepted.
        self.assertTrue(jail.is_contained("/home/alice/sub", "/home/alice",
                                          case_sensitive=True))
        self.assertFalse(jail.is_contained("/home/alice2/sub", "/home/alice",
                                           case_sensitive=True))


if __name__ == "__main__":
    unittest.main()
