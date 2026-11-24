"""Regression contract for hostile focus-decision reasons in the session snapshot.

A GRANTED decision is the only focus status that can keep the composed
session-lifecycle record at STATUS_OK. The broker only attaches a reason to
DENIED and ACTIVATION_FAILED decisions, so a GRANTED decision carrying a
failure reason (or a hostile non-string reason) is a contradictory record that
must fail closed instead of claiming a ready/safe session.
"""

import unittest

from canopy_features.reliability import lock_session_events as lock
from canopy_features.reliability import session_lifecycle_snapshot as snapshot
from canopy_features.reliability import theme_transition_rollback as theme
from canopy_features.windows import focus_intents as focus


class _BrokerWithHistory(focus.FocusBroker):
    """A bounded hostile source exposing caller-supplied decision history."""

    def __init__(self, decisions):
        super().__init__(lambda *_: True)
        self._hostile_history = tuple(decisions)

    @property
    def history(self):
        return self._hostile_history


def _decision(status, reason=""):
    ref = focus.WindowRef(10, 1)
    intent = focus.FocusIntent("owner.app", ref)
    return focus.FocusDecision(status, intent, "owner.app", reason)  # pyright: ignore[reportArgumentType]


def _compose(decision):
    return snapshot.compose(
        lock.Reconciler(initial_locked=False),
        theme.ThemeTransitionRollback(),
        _BrokerWithHistory((decision,)),
    )


class SessionLifecycleGrantedReasonTests(unittest.TestCase):
    def test_granted_with_failure_reason_is_rejected(self):
        reason = "backend error: RuntimeError"
        self.assertLessEqual(len(reason), snapshot.MAX_CHARS)
        with self.assertRaises(snapshot.SnapshotError):
            _compose(_decision(focus.GRANTED, reason))

    def test_granted_with_hostile_non_string_reason_is_rejected(self):
        with self.assertRaises(snapshot.SnapshotError):
            _compose(_decision(focus.GRANTED, ["backend error"]))

    def test_failure_reason_still_blocks(self):
        record = _compose(_decision(
            focus.DENIED, "backend error: RuntimeError"))
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)


if __name__ == "__main__":
    unittest.main()
