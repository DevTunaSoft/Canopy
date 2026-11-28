"""Native host-event ceiling contracts (PR #728 epoch/episode adaptation).

SYNTHETIC: pure in-process records driven by real protocol-v2 HostEvents.
No desktop, Qt, producer I/O, clock, timer, poll, thread, queue or screen
reader is exercised. These tests pin that an event ceiling is an epoch bound
reconciled by the next real event, and that recovery/rebuild budgets rebase
only on explicit host conditions while retained state stays hard-bounded.
"""
import unittest
from pathlib import Path

from canopy_core.host_events import HostEvents
from canopy_features.reliability import native_host_event_ceilings as ceilings

MODULE = Path(ceilings.__file__)
CATALOG = ceilings.REFRESH_TOPIC


def catalog_bus():
    seen = []
    callback = seen.append
    bus = HostEvents({CATALOG: [callback]})
    bus.subscribe(CATALOG, callback)
    return bus, seen


class NativeHostEventCeilingTests(unittest.TestCase):
    def test_epoch_reconciles_newest_authoritative_state_past_64(self):
        authoritative = ["org.example.One.desktop"]
        controller = ceilings.RefreshEpochController(
            lambda: tuple(authoritative))
        bus, seen = catalog_bus()
        outcomes = []
        for sequence in range(1, 201):
            if sequence in (65, 129, 193):
                authoritative.append("org.example.Beta%d.desktop" % sequence)
            result = bus.emit(CATALOG, {"count": sequence})
            self.assertEqual(result.delivered, 1)
            report = controller.observe(result.event)
            self.assertIn(report.outcome, ceilings.FIXED_OUTCOMES)
            self.assertNotEqual(report.outcome, "refresh_limit")
            outcomes.append(report.outcome)
        self.assertEqual(len(seen), 200)
        self.assertEqual(controller.event_count, 200)
        self.assertEqual(controller.producer_calls, 200)
        self.assertEqual(controller.epoch_events, 8)
        self.assertEqual(controller.reconciliations, 3)
        self.assertEqual(controller.authoritative_state,
                         tuple(authoritative))
        self.assertEqual(outcomes[64], ceilings.OUTCOME_REFRESHED)
        self.assertEqual(outcomes[128], ceilings.OUTCOME_REFRESHED)
        self.assertEqual(outcomes[192], ceilings.OUTCOME_REFRESHED)
        self.assertEqual(len(controller.reports), ceilings.MAX_REPORT_HISTORY)
        self.assertTrue(controller.connected)
        bus.close()
        controller.close()

    def test_refusal_is_atomic_and_replayed_or_foreign_events_rejected(self):
        calls = []

        def producer():
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("hostile producer text SENSITIVE")
            return ("org.example.One.desktop",)

        controller = ceilings.RefreshEpochController(producer)
        bus, _ = catalog_bus()
        first = bus.emit(CATALOG, {"count": 1})
        self.assertEqual(controller.observe(first.event).outcome,
                         ceilings.OUTCOME_REFRESHED)
        before = controller.authoritative_state
        second = bus.emit(CATALOG, {"count": 2})
        refused = controller.observe(second.event)
        self.assertEqual(refused.outcome, ceilings.OUTCOME_REFUSED)
        self.assertEqual(controller.authoritative_state, before)
        replayed = controller.observe(first.event)
        self.assertEqual(replayed.outcome, ceilings.OUTCOME_REJECTED)
        self.assertEqual(replayed.reason, "REPLAYED_SEQUENCE")
        self.assertEqual(controller.producer_calls, 2)
        self.assertEqual(controller.rejection_count, 1)
        for report in controller.reports:
            self.assertNotIn("SENSITIVE", repr(report))
        bus.close()

    def test_episode_recovery_budget_rebases_only_on_explicit_condition(self):
        budget = ceilings.EpisodeRecoveryBudget(max_grants=4)
        self.assertEqual([budget.grant() for _ in range(4)],
                         ["RECOVERY_GRANTED"] * 4)
        self.assertEqual(budget.grant(), "CAPACITY")
        self.assertEqual((budget.episode_grants, budget.grants_total,
                          budget.episodes), (4, 4, 0))
        budget.new_episode()
        self.assertEqual(budget.grant(), "RECOVERY_GRANTED")
        self.assertEqual((budget.episode_grants, budget.grants_total,
                          budget.episodes), (1, 5, 1))
        for _ in range(3):
            budget.grant()
        self.assertEqual(budget.grant(), "CAPACITY")
        self.assertEqual(budget.grants_total, 8)

    def test_episode_rebuild_budget_keeps_retained_state_bounded(self):
        budget = ceilings.EpisodeRebuildBudget(cap=10, per_episode=4)
        budget.rebuild(9)
        budget.shed()
        self.assertEqual((budget.retained, budget.rebuilt), (0, 0))
        budget.normal_transition()
        self.assertEqual(budget.rebuild(6), 4)
        self.assertEqual(budget.rebuild(2), 0)
        budget.normal_transition()
        self.assertEqual(budget.rebuild(3), 3)
        self.assertEqual((budget.retained, budget.rebuilt, budget.generations),
                         (7, 3, 2))
        budget.close()
        self.assertEqual(budget.rebuild(1), 0)
        self.assertEqual(budget.retained, 0)

    def test_hostile_bounds_and_source_have_no_wakeup(self):
        with self.assertRaises(ceilings.CeilingError):
            ceilings.RefreshEpochController(None)
        with self.assertRaises(ceilings.CeilingError):
            ceilings.RefreshEpochController(lambda: (), max_events=65)
        with self.assertRaises(ceilings.CeilingError):
            ceilings.EpisodeRecoveryBudget(max_grants=0)
        controller = ceilings.RefreshEpochController(lambda: ["x" * 65])
        bus, _ = catalog_bus()
        result = bus.emit(CATALOG, {"count": 1})
        self.assertEqual(controller.observe(result.event).outcome,
                         ceilings.OUTCOME_REFUSED)
        bus.close()
        code = MODULE.read_text(encoding="utf-8")
        for forbidden in ("sleep(", "QTimer", "Thread(", "poll(",
                          "while True", "import os", "import time",
                          "refresh_limit", "deque(maxlen=64)"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)
        for marker in ("_epoch_events", "_reconciliations", "new_episode",
                       "normal_transition", "MAX_REPORT_HISTORY"):
            with self.subTest(marker=marker):
                self.assertIn(marker, code)


if __name__ == "__main__":
    unittest.main()
