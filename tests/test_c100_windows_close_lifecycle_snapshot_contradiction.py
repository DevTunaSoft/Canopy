"""Regression tests for close-lifecycle status/visible cross-field contradictions.

On unfixed code a caller can hand ``compose`` a decision whose lifecycle status
contradicts its durable visibility flag (for example ``CLOSED`` with
``visible=True``). The module embeds both fields verbatim, producing a record
that jointly claims the window is parked and still shown. These tests pin the
fail-closed guard on that cross-field contract.
"""

import unittest

from canopy_features.windows import focus_intents as focus
from canopy_features.windows import switcher_state as switcher
from canopy_features.windows import window_close_intents as close


def _m():
    from canopy_features.windows import close_lifecycle_snapshot as module
    return module


def _close_model():
    model = close.CloseIntentModel()
    model.register("files.win", "shell.owner", state={"page": "home"})
    return model


def _switcher():
    state = switcher.SwitcherState([10, 20, 30], current=10)
    state.begin()
    state.next()
    return state.snapshot()


def _quiet_focus():
    return focus.FocusBroker(lambda *_: True)


def _decision(status, visible, note=""):
    return close.IntentResult("files.win", status, visible, close.NO_STATE,
                              note)


def _compose(decisions):
    return _m().compose(_close_model(), _switcher(), _quiet_focus(),
                        decisions)


class CloseLifecycleContradictionTests(unittest.TestCase):
    def test_contradictory_status_visible_pairs_rejected(self):
        # A parked/already-parked window must be hidden; a restored/already
        # shown window must be visible; a guarded window was left open. Each
        # pair below is individually well-typed but jointly asserts a false
        # lifecycle state and must fail closed with the module's domain error.
        bad = (
            (close.CLOSED, True),
            (close.ALREADY_CLOSED, True),
            (close.REOPENED, False),
            (close.ALREADY_OPEN, False),
            (close.GUARDED, False),
        )
        for status, visible in bad:
            with self.subTest(status=status, visible=visible):
                with self.assertRaises(_m().SnapshotError):
                    _compose((_decision(status, visible,
                                        "window parked; state preserved"),))

    def test_consistent_pairs_still_compose(self):
        good = (
            (close.CLOSED, False),
            (close.ALREADY_CLOSED, False),
            (close.REOPENED, True),
            (close.ALREADY_OPEN, True),
            (close.GUARDED, True),
        )
        for status, visible in good:
            with self.subTest(status=status, visible=visible):
                record = _compose((_decision(status, visible),))
                self.assertEqual(record.close.statuses, (status,))
                self.assertEqual(record.close.visible_flags, (visible,))

    def test_unknown_visibility_is_accepted(self):
        # ``None`` is the canonical refusal form (no visibility observation),
        # and must not be mistaken for a contradictory boolean.
        for status in (close.CLOSED, close.UNKNOWN_WINDOW,
                       close.OWNERSHIP_DENIED, close.GUARDED):
            with self.subTest(status=status):
                record = _compose((_decision(status, None),))
                self.assertEqual(record.close.visible_flags, (None,))

    def test_contradiction_beyond_embedding_cap_rejected(self):
        # Cross-field validity applies to the whole supplied history, just as
        # the existing hard-refusal guard does; capping the embedded view must
        # not smuggle an impossible lifecycle claim past validation.
        # Filler decisions are consistent and use distinct, bounded ids.
        consistent = tuple(
            close.IntentResult("w%d.win" % i, close.CLOSED, False,
                               close.NO_STATE, "")
            for i in range(_m().MAX_DECISIONS))
        decisions = (_decision(close.CLOSED, True),) + consistent
        with self.assertRaises(_m().SnapshotError):
            _compose(decisions)


if __name__ == "__main__":
    unittest.main()
