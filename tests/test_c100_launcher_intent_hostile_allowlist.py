"""Fail-closed contract for hostile host allowlists in launcher intent summaries.

A launcher decision must never leak a raw exception from a caller-supplied
allowlist: an allowlist that cannot be read is simply not an approval. These
tests are pure/offline; no Qt, GIO, process launch or desktop is involved.
"""
import unittest

from canopy_features.launcher.launcher_intent_summary import (
    STATUS_NOT_APPROVED,
    STATUS_READY,
    summarize_launcher_intent,
)

CATALOG = (
    ("safe.desktop", "Firefox"),
    ("other.desktop", "Files"),
)


class ExplodingAllowlist:
    """A lazy, config-backed allowlist that fails while being read."""

    def __init__(self, exc=None):
        self.exc = exc if exc is not None else OSError("allowlist source unavailable")
        self.consumed = 0

    def __iter__(self):
        return self

    def __next__(self):
        self.consumed += 1
        raise self.exc


class HostileAllowlistFailClosedTests(unittest.TestCase):
    """Any allowlist read failure yields NOT_APPROVED with no argv."""

    def test_allowlist_read_failure_is_fail_closed(self):
        allowlist = ExplodingAllowlist()
        result = summarize_launcher_intent(
            "firefox", CATALOG, allowed_app_ids=allowlist)
        self.assertEqual(result.status, STATUS_NOT_APPROVED)
        self.assertEqual(result.argv, ())
        self.assertEqual(result.selected_app_id, "safe.desktop")
        self.assertGreaterEqual(allowlist.consumed, 1)

    def test_runtime_error_in_allowlist_does_not_escape(self):
        result = summarize_launcher_intent(
            "firefox", CATALOG,
            allowed_app_ids=ExplodingAllowlist(RuntimeError("boom")),
        )
        self.assertEqual(result.status, STATUS_NOT_APPROVED)
        self.assertEqual(result.argv, ())
        self.assertEqual(result.selected_app_id, "safe.desktop")

    def test_blank_query_allowlist_failure_is_fail_closed(self):
        result = summarize_launcher_intent(
            "", CATALOG, favorites=("other.desktop",),
            allowed_app_ids=ExplodingAllowlist(),
        )
        self.assertEqual(result.status, STATUS_NOT_APPROVED)
        self.assertEqual(result.argv, ())
        self.assertEqual(result.selected_app_id, "other.desktop")

    def test_approved_allowlist_still_yields_ready(self):
        result = summarize_launcher_intent(
            "firefox", CATALOG, allowed_app_ids={"safe.desktop"})
        self.assertEqual(result.status, STATUS_READY)
        self.assertEqual(result.argv, ("gio", "launch", "--", "safe.desktop"))


if __name__ == "__main__":
    unittest.main()
