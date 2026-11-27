"""PE-054 RED/GREEN contract tests for simulated low-memory cache shedding.

Every condition here is caller-supplied simulation input. The module under
test never reads real memory, polls, starts services or observes the OS.
"""

import inspect
import unittest

from canopy_features.reliability import low_memory_contracts as lm


class DecisionTests(unittest.TestCase):
    def test_decide_allows_population_only_when_normal(self):
        boundary = lm.CacheBoundary("notices", 8)
        normal = lm.decide(lm.CONDITION_NORMAL, boundary)
        self.assertFalse(normal.shed)
        self.assertTrue(normal.allow_populate)
        self.assertEqual(normal.retained_entries, 8)
        low = lm.decide(lm.CONDITION_LOW, boundary)
        self.assertTrue(low.shed)
        self.assertFalse(low.allow_populate)
        self.assertEqual(low.retained_entries, 0)
        self.assertEqual(low.reason, lm.SHED_LOW_MEMORY)
        unknown = lm.decide(lm.CONDITION_UNKNOWN, boundary)
        self.assertTrue(unknown.shed)
        self.assertEqual(unknown.reason, lm.SHED_UNKNOWN)

    def test_decide_rejects_wrong_types_with_domain_error(self):
        boundary = lm.CacheBoundary("notices", 8)
        for bad in (None, 7, True, b"NORMAL", ["NORMAL"]):
            with self.assertRaises(lm.LowMemoryError):
                lm.decide(bad, boundary)
        with self.assertRaises(lm.LowMemoryError):
            lm.decide(lm.CONDITION_NORMAL, "notices")


class SheddingTests(unittest.TestCase):
    def test_low_condition_sheds_caches_and_refuses_population(self):
        controller = lm.LowMemoryCacheController()
        self.assertTrue(controller.snapshot().shedding)
        controller.observe(lm.CONDITION_NORMAL)
        self.assertEqual(controller.populate("delivery_notices", ("a", "b")), 2)
        self.assertEqual(controller.values("delivery_notices"), ("a", "b"))
        decision = controller.observe(lm.CONDITION_LOW)
        self.assertTrue(decision.shed)
        self.assertFalse(decision.allow_populate)
        snap = controller.snapshot()
        self.assertTrue(snap.shedding)
        self.assertTrue(all(b.retained == 0 for b in snap.boundaries))
        self.assertEqual(controller.values("delivery_notices"), ())
        self.assertEqual(controller.populate("delivery_notices", ("c",)), 0)
        self.assertEqual(controller.values("delivery_notices"), ())

    def test_unknown_condition_is_fail_closed_shed(self):
        controller = lm.LowMemoryCacheController()
        controller.observe(lm.CONDITION_NORMAL)
        controller.populate("switcher_windows", (1, 2, 3))
        decision = controller.observe(lm.CONDITION_UNKNOWN)
        self.assertEqual(decision.reason, lm.SHED_UNKNOWN)
        self.assertTrue(controller.snapshot().shedding)
        self.assertEqual(controller.values("switcher_windows"), ())

    def test_repeated_same_condition_does_not_double_count_sheds(self):
        controller = lm.LowMemoryCacheController()
        controller.observe(lm.CONDITION_NORMAL)
        controller.observe(lm.CONDITION_LOW)
        first = controller.snapshot().shed_count
        controller.observe(lm.CONDITION_LOW)
        self.assertEqual(controller.snapshot().shed_count, first)


class BoundedRecoveryTests(unittest.TestCase):
    def _small(self, budget=3, max_rebuilt=6):
        boundaries = (lm.CacheBoundary("a", 4), lm.CacheBoundary("b", 4))
        return lm.LowMemoryCacheController(boundaries, recovery_budget=budget,
                                           max_rebuilt=max_rebuilt)

    def test_recovery_grants_limited_credits_per_round(self):
        controller = self._small()
        controller.observe(lm.CONDITION_NORMAL)
        self.assertEqual(controller.populate("a", (1, 2, 3, 4)), 3)
        self.assertEqual(controller.populate("b", (9,)), 0)
        step = controller.advance_recovery()
        self.assertEqual(step.granted, 3)
        self.assertEqual(step.round, 2)
        self.assertFalse(step.done)
        self.assertEqual(controller.populate("b", (9, 10)), 2)
        self.assertEqual(controller.values("b"), (9, 10))
        self.assertEqual(controller.snapshot().rebuilt_entries, 5)

    def test_recovery_rounds_are_bounded(self):
        controller = self._small(budget=2, max_rebuilt=100)
        controller.observe(lm.CONDITION_NORMAL)
        for _ in range(lm.MAX_RECOVERY_ROUNDS + 5):
            step = controller.advance_recovery()
        self.assertTrue(step.done)
        self.assertEqual(step.granted, 0)
        self.assertEqual(controller.snapshot().recovery_round,
                         lm.MAX_RECOVERY_ROUNDS)

    def test_lifetime_rebuilt_total_is_bounded(self):
        controller = self._small(budget=3, max_rebuilt=5)
        controller.observe(lm.CONDITION_NORMAL)
        self.assertEqual(controller.populate("a", (1, 2, 3)), 3)
        controller.advance_recovery()
        self.assertEqual(controller.populate("b", (4, 5, 6)), 2)
        controller.advance_recovery()
        self.assertEqual(controller.populate("a", (7,)), 0)
        self.assertEqual(controller.snapshot().rebuilt_entries, 5)
        self.assertTrue(controller.advance_recovery().done)

    def test_reshedding_clears_credits_and_entries(self):
        controller = self._small()
        controller.observe(lm.CONDITION_NORMAL)
        controller.populate("a", (1, 2))
        controller.observe(lm.CONDITION_LOW)
        controller.observe(lm.CONDITION_NORMAL)
        snap = controller.snapshot()
        self.assertEqual(snap.recovery_count, 2)
        self.assertTrue(all(b.retained == 0 for b in snap.boundaries))
        self.assertEqual(snap.rebuilt_entries, 2)


class FailClosedInputTests(unittest.TestCase):
    def test_boundary_validation(self):
        for name, cap in (("", 4), (None, 4), (7, 4), ("x", 0),
                          ("x", -1), ("x", lm.MAX_ENTRIES_PER_BOUNDARY + 1),
                          ("x", True), ("x", 4.0)):
            with self.assertRaises(lm.LowMemoryError):
                lm.CacheBoundary(name, cap)

    def test_controller_rejects_duplicate_names_oversized_totals_and_bad_budget(self):
        dup = (lm.CacheBoundary("a", 2), lm.CacheBoundary("a", 2))
        with self.assertRaises(lm.LowMemoryError):
            lm.LowMemoryCacheController(dup)
        with self.assertRaises(lm.LowMemoryError):
            lm.LowMemoryCacheController("notices")
        with self.assertRaises(lm.LowMemoryError):
            lm.LowMemoryCacheController(())
        with self.assertRaises(lm.LowMemoryError):
            lm.LowMemoryCacheController(recovery_budget=0)
        with self.assertRaises(lm.LowMemoryError):
            lm.LowMemoryCacheController(
                (lm.CacheBoundary("a", lm.MAX_ENTRIES_PER_BOUNDARY),
                 lm.CacheBoundary("b", lm.MAX_ENTRIES_PER_BOUNDARY)),
                max_rebuilt=lm.MAX_REBUILT_TOTAL + 1)

    def test_populate_rejects_unknown_names_wrong_types_and_oversized_input(self):
        controller = self.small()
        controller.observe(lm.CONDITION_NORMAL)
        for name in ("missing", None, 7, b"a"):
            with self.assertRaises(lm.LowMemoryError):
                controller.populate(name, (1,))
        for entries in ([1, 2], "ab", None, 7):
            with self.assertRaises(lm.LowMemoryError):
                controller.populate("a", entries)
        with self.assertRaises(lm.LowMemoryError):
            controller.populate("a", (1, 2, 3, 4, 5))
        self.assertEqual(controller.values("a"), ())

    def test_invalid_condition_does_not_change_state(self):
        controller = self.small()
        controller.observe(lm.CONDITION_NORMAL)
        controller.populate("a", (1, 2))
        for bad in (None, 7, True, b"NORMAL", "degraded"):
            with self.assertRaises(lm.LowMemoryError):
                controller.observe(bad)
        snap = controller.snapshot()
        self.assertEqual(snap.condition, lm.CONDITION_NORMAL)
        self.assertFalse(snap.shedding)
        self.assertEqual(controller.values("a"), (1, 2))

    @staticmethod
    def small():
        return lm.LowMemoryCacheController((lm.CacheBoundary("a", 4),))


class SnapshotAndSimulationTests(unittest.TestCase):
    def test_snapshot_is_deterministic_sorted_and_read_only(self):
        def run():
            c = lm.LowMemoryCacheController()
            c.observe(lm.CONDITION_NORMAL)
            c.populate("switcher_windows", (1, 2))
            c.populate("delivery_notices", ("n",))
            return c.snapshot()
        first, second = run(), run()
        self.assertEqual(first, second)
        self.assertEqual([b.name for b in first.boundaries],
                         sorted(b.name for b in first.boundaries))
        view = first.to_dict()
        self.assertIsInstance(view, type(first.to_dict()))
        with self.assertRaises(TypeError):
            view["condition"] = lm.CONDITION_LOW

    def test_record_is_labeled_not_established(self):
        snap = lm.LowMemoryCacheController().snapshot()
        self.assertEqual(snap.acceptance, lm.ACCEPTANCE_NOT_ESTABLISHED)
        self.assertIn("acceptance", snap.to_dict())

    def test_module_observes_no_real_memory(self):
        source = inspect.getsource(lm)
        for token in ("psutil", "getrusage", "/proc", "ctypes",
                      "import os", "from os", "time."):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
