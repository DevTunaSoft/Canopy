"""Offline tests for the no-duplication theme transition rollback model.

No Qt, compositor, Mint session or compiled binary is involved. These tests
run on the Windows host with the repository's Python interpreter only.
"""

import unittest

from canopy_features.reliability.theme_transition_rollback import (
    IDLE,
    PREPARED,
    ThemeTransitionRollback,
)


class ThemeTransitionRollbackTests(unittest.TestCase):
    def make_ledger(self, theme="classic", resources=("theme.qml", "dock.cache")):
        return ThemeTransitionRollback(theme, resources)

    def test_initial_state_has_one_active_theme_and_no_candidate(self):
        ledger = self.make_ledger()
        snap = ledger.snapshot()
        self.assertEqual(snap.state, IDLE)
        self.assertEqual(snap.active, "classic")
        self.assertIsNone(snap.candidate)
        self.assertEqual(snap.live_resources, {"theme.qml", "dock.cache"})
        self.assertEqual(snap.abandoned_resources, frozenset())
        self.assertTrue(snap.single_owner)

    def test_prepare_creates_one_candidate_without_duplicating_active(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.prepare("modern", {"modern.qml"}), "PREPARED")
        snap = ledger.snapshot()
        self.assertEqual(snap.state, PREPARED)
        self.assertEqual(snap.active, "classic")
        self.assertEqual(snap.candidate, "modern")
        self.assertEqual(snap.live_resources,
                         {"theme.qml", "dock.cache", "modern.qml"})
        self.assertTrue(snap.single_owner)

    def test_second_concurrent_prepare_is_rejected_no_duplicate_candidate(self):
        ledger = self.make_ledger()
        ledger.prepare("modern", {"modern.qml"})
        self.assertEqual(ledger.prepare("minimal", {"minimal.qml"}), "BUSY")
        snap = ledger.snapshot()
        self.assertEqual(snap.candidate, "modern")
        self.assertNotIn("minimal.qml", snap.live_resources)
        self.assertEqual(snap.active, "classic")

    def test_prepare_rejects_resource_already_owned_by_active_theme(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.prepare("modern", {"theme.qml"}),
                         "DUPLICATE_RESOURCE")
        snap = ledger.snapshot()
        self.assertIsNone(snap.candidate)
        self.assertEqual(snap.active, "classic")
        self.assertEqual(snap.abandoned_resources, frozenset())

    def test_prepare_rejects_duplicate_names_within_one_batch(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.prepare("modern", ["a.qml", "a.qml"]),
                         "INVALID_RESOURCES")
        self.assertIsNone(ledger.snapshot().candidate)

    def test_prepare_rejects_abandoned_resource_until_reclaimed(self):
        ledger = self.make_ledger()
        ledger.prepare("modern", {"modern.qml"})
        ledger.interrupt()
        self.assertEqual(ledger.prepare("other", {"modern.qml"}),
                         "DUPLICATE_RESOURCE")
        ledger.reclaim_abandoned()
        self.assertEqual(ledger.prepare("other", {"modern.qml"}), "PREPARED")

    def test_commit_promotes_candidate_and_abandons_previous_resources(self):
        ledger = self.make_ledger()
        ledger.prepare("modern", {"modern.qml"})
        self.assertEqual(ledger.commit(), "COMMITTED")
        snap = ledger.snapshot()
        self.assertEqual(snap.state, IDLE)
        self.assertEqual(snap.active, "modern")
        self.assertIsNone(snap.candidate)
        self.assertEqual(snap.live_resources, {"modern.qml"})
        self.assertEqual(snap.abandoned_resources, {"theme.qml", "dock.cache"})
        self.assertTrue(snap.single_owner)

    def test_reclaim_hands_abandoned_resources_out_exactly_once(self):
        ledger = self.make_ledger()
        ledger.prepare("modern", {"modern.qml"})
        ledger.commit()
        self.assertEqual(ledger.reclaim_abandoned(),
                         {"theme.qml", "dock.cache"})
        self.assertEqual(ledger.reclaim_abandoned(), frozenset())
        self.assertEqual(ledger.snapshot().abandoned_resources, frozenset())

    def test_interrupted_transition_rolls_back_and_abandons_candidate(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.prepare("modern", {"modern.qml", "hint.token"}),
                         "PREPARED")
        self.assertEqual(ledger.interrupt(), "ROLLED_BACK")
        snap = ledger.snapshot()
        self.assertEqual(snap.state, IDLE)
        self.assertEqual(snap.active, "classic")
        self.assertIsNone(snap.candidate)
        self.assertEqual(snap.live_resources, {"theme.qml", "dock.cache"})
        self.assertEqual(snap.abandoned_resources,
                         {"modern.qml", "hint.token"})
        self.assertTrue(snap.single_owner)
        self.assertEqual(ledger.reclaim_abandoned(),
                         {"modern.qml", "hint.token"})

    def test_interrupted_transition_never_activates_candidate(self):
        ledger = self.make_ledger()
        for target in ("modern", "minimal", "other"):
            ledger.prepare(target, {target + ".qml"})
            ledger.interrupt()
            self.assertEqual(ledger.snapshot().active, "classic")
            self.assertIsNone(ledger.snapshot().candidate)
            ledger.reclaim_abandoned()
        self.assertEqual(ledger.snapshot().live_resources,
                         {"theme.qml", "dock.cache"})
        self.assertEqual(ledger.snapshot().abandoned_resources, frozenset())

    def test_aba_sequence_keeps_single_owner_across_both_commits(self):
        ledger = self.make_ledger()
        ledger.prepare("modern", {"modern.qml"})
        ledger.commit()
        ledger.reclaim_abandoned()

        self.assertEqual(ledger.prepare("classic", {"theme.qml"}), "PREPARED")
        self.assertEqual(ledger.commit(), "COMMITTED")
        snap = ledger.snapshot()
        self.assertEqual(snap.active, "classic")
        self.assertEqual(snap.live_resources, {"theme.qml"})
        self.assertEqual(snap.abandoned_resources, {"modern.qml"})
        self.assertTrue(snap.single_owner)
        ledger.reclaim_abandoned()

    def test_commit_and_interrupt_without_candidate_are_noops(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.commit(), "NO_CANDIDATE")
        self.assertEqual(ledger.interrupt(), "NO_CANDIDATE")
        snap = ledger.snapshot()
        self.assertEqual(snap.state, IDLE)
        self.assertEqual(snap.active, "classic")
        self.assertEqual(snap.abandoned_resources, frozenset())
        self.assertEqual(ledger.reclaim_abandoned(), frozenset())

    def test_invalid_theme_and_resource_inputs_are_rejected(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.prepare("", {"x"}), "INVALID_THEME")
        self.assertEqual(ledger.prepare("modern", [""]), "INVALID_RESOURCES")
        self.assertEqual(ledger.prepare("modern", [1]), "INVALID_RESOURCES")
        with self.assertRaises(ValueError):
            ThemeTransitionRollback("classic", ["a", "a"])

    def test_abandoned_ledger_is_bounded_and_forces_reclaim(self):
        ledger = ThemeTransitionRollback("base", ("r0",))
        for index in range(1, ledger.MAX_ABANDONED + 1):
            self.assertEqual(ledger.prepare("t%d" % index, {"r%d" % index}),
                             "PREPARED")
            self.assertEqual(ledger.interrupt(), "ROLLED_BACK")
        snap = ledger.snapshot()
        self.assertEqual(len(snap.abandoned_resources), ledger.MAX_ABANDONED)
        self.assertTrue(snap.single_owner)
        self.assertEqual(ledger.prepare("extra", {"extra"}), "RECLAIM_REQUIRED")
        self.assertIsNone(ledger.snapshot().candidate)
        ledger.reclaim_abandoned()
        self.assertEqual(ledger.prepare("extra", {"extra"}), "PREPARED")

    def test_model_has_no_timers_threads_or_services(self):
        from canopy_features.reliability import theme_transition_rollback as mod
        from pathlib import Path

        source = Path(mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("import time", "import threading", "import socket",
                          "import subprocess", "while True", "sleep("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
