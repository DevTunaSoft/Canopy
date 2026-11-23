"""Regression: filesystem-view faults must collapse to fail-closed decisions.

``WorkingDirectoryPolicy.evaluate`` is a pure evaluator that promises a bounded
Decision for every request. A host-supplied read-only filesystem view may signal
a symlink loop, an undecodable path, or a transient query failure with
RuntimeError/ValueError/TypeError instead of OSError. Those faults must be
reported as REJECTED decisions, never propagate out of the evaluator.

No process launch, no real I/O, no QML and no visual change.
"""
import unittest

from canopy_features.apps.working_directory_policy import (
    WorkingDirectoryPolicy,
)

ROOT = "/home/user"


class FaultyFilesystem:
    """Injected view that raises a chosen fault from one query method."""

    def __init__(self, *, resolve_exc=None, is_directory_exc=None):
        self.resolve_exc = resolve_exc
        self.is_directory_exc = is_directory_exc
        self.directories = frozenset((ROOT,))

    def is_directory(self, path):
        if self.is_directory_exc is not None:
            raise self.is_directory_exc
        return path in self.directories

    def resolve(self, path):
        if self.resolve_exc is not None:
            raise self.resolve_exc
        return path


class FilesystemFaultFailClosedTests(unittest.TestCase):
    FAULTS = (
        RuntimeError("symlink loop"),
        ValueError("undecodable path"),
        TypeError("bad view argument"),
    )

    def policy(self, fs):
        return WorkingDirectoryPolicy((ROOT,), filesystem=fs, flavor="posix")

    def assert_rejected(self, decision, reason):
        self.assertEqual(decision.status, "REJECTED")
        self.assertEqual(decision.reason, reason)
        self.assertIsNone(decision.path)
        self.assertFalse(decision.allowed)

    def test_resolve_fault_explicit_request_rejected_not_raised(self):
        for fault in self.FAULTS:
            with self.subTest(fault=type(fault).__name__):
                policy = self.policy(FaultyFilesystem(resolve_exc=fault))
                decision = policy.evaluate(ROOT, ROOT)
                self.assert_rejected(decision, "OUTSIDE_ALLOWED_ROOT")

    def test_resolve_fault_inherited_request_rejected_not_raised(self):
        for fault in self.FAULTS:
            with self.subTest(fault=type(fault).__name__):
                policy = self.policy(FaultyFilesystem(resolve_exc=fault))
                decision = policy.evaluate(None, ROOT)
                self.assert_rejected(decision, "UNSAFE_INHERITANCE")

    def test_is_directory_fault_explicit_request_rejected_not_raised(self):
        for fault in self.FAULTS:
            with self.subTest(fault=type(fault).__name__):
                policy = self.policy(FaultyFilesystem(is_directory_exc=fault))
                decision = policy.evaluate(ROOT, ROOT)
                self.assert_rejected(decision, "MISSING_DIRECTORY")

    def test_is_directory_fault_inherited_request_rejected_not_raised(self):
        for fault in self.FAULTS:
            with self.subTest(fault=type(fault).__name__):
                policy = self.policy(FaultyFilesystem(is_directory_exc=fault))
                decision = policy.evaluate(None, ROOT)
                self.assert_rejected(decision, "UNSAFE_INHERITANCE")

    def test_healthy_view_still_allows_bound_decision(self):
        # Negative control: the fail-closed path must not reject a healthy view.
        policy = self.policy(FaultyFilesystem())
        decision = policy.evaluate(ROOT, ROOT)
        self.assertEqual(decision.status, "ALLOWED")
        self.assertEqual(decision.path, ROOT)


if __name__ == "__main__":
    unittest.main()
