"""Offline model tests; no Qt, no desktop, no Mint or rendering claims."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.accessibility.reduced_motion_contract import (
    DEFAULT_SOURCE, FULL, MAX_CONSUMERS, MAX_PRESENTATIONS, PRESENTATION,
    REDUCE, SYSTEM, UNSET, USER, MotionContractError, ReducedMotionContract,
    resolve,
)


class ResolveTests(unittest.TestCase):
    def test_unset_preference_fails_safe_to_reduce(self):
        decision = resolve()
        self.assertTrue(decision.reduced)
        self.assertFalse(decision.motion_allowed)
        self.assertEqual(decision.source, DEFAULT_SOURCE)
        self.assertTrue(decision.from_default)
        self.assertEqual(decision.conflicts, ())
        self.assertEqual(decision.unset_sources, (SYSTEM, USER, PRESENTATION))
        self.assertEqual(resolve(UNSET, UNSET, UNSET), decision)

    def test_explicit_precedence_allows_motion_when_all_sources_agree(self):
        decision = resolve(FULL, FULL, FULL)
        self.assertTrue(decision.motion_allowed)
        self.assertFalse(decision.reduced)
        self.assertEqual(decision.source, PRESENTATION)
        self.assertEqual(decision.conflicts, ())
        self.assertEqual(decision.unset_sources, ())
        self.assertFalse(decision.from_default)
        self.assertEqual(resolve(FULL, UNSET, UNSET).source, SYSTEM)
        self.assertEqual(resolve(UNSET, FULL, UNSET).source, USER)

    def test_contradictory_overrides_never_re_enable_motion(self):
        cases = (
            ((REDUCE, FULL, UNSET), SYSTEM, (USER,)),
            ((FULL, REDUCE, UNSET), USER, (SYSTEM,)),
            ((REDUCE, UNSET, FULL), SYSTEM, (PRESENTATION,)),
            ((FULL, FULL, REDUCE), PRESENTATION, (SYSTEM, USER)),
        )
        for values, expected_source, expected_conflicts in cases:
            with self.subTest(values=values):
                decision = resolve(*values)
                self.assertTrue(decision.reduced)
                self.assertEqual(decision.source, expected_source)
                self.assertEqual(decision.conflicts, expected_conflicts)
                self.assertFalse(decision.motion_allowed)

    def test_mixed_unset_and_conflict_are_reported_together(self):
        decision = resolve(FULL, UNSET, REDUCE)
        self.assertTrue(decision.reduced)
        self.assertEqual(decision.source, PRESENTATION)
        self.assertEqual(decision.unset_sources, (USER,))
        self.assertEqual(decision.conflicts, (SYSTEM,))

    def test_invalid_preferences_fail_closed(self):
        for bad in (None, "YES", "", "Reduce", 1, True, [], {}, b"reduce"):
            for position in range(3):
                with self.subTest(bad=repr(bad), position=position):
                    values = [UNSET, UNSET, UNSET]
                    values[position] = bad
                    with self.assertRaises(MotionContractError):
                        resolve(*values)

    def test_decision_is_immutable_and_event_fields_are_scalar(self):
        decision = resolve(REDUCE, FULL, UNSET)
        with self.assertRaises(FrozenInstanceError):
            decision.reduced = False
        fields = decision.as_event_fields()
        self.assertEqual(set(fields), {
            "reduced", "source", "conflict_count", "unset_count", "from_default"})
        for key, value in fields.items():
            self.assertEqual(key, key.lower())
            self.assertIsInstance(value, (bool, str, int))
        self.assertEqual(fields["conflict_count"], 1)
        self.assertEqual(fields["unset_count"], 1)
        self.assertIs(fields["reduced"], True)


class PropagationTests(unittest.TestCase):
    def setUp(self):
        self.contract = ReducedMotionContract()

    def test_update_reaches_every_consumer_and_reports_only_changes(self):
        self.contract.register("classic")
        self.contract.register("modern")
        first = self.contract.update(system=REDUCE)
        self.assertEqual(first.version, 1)
        self.assertEqual(first.changed, ("classic", "modern"))
        self.assertEqual(set(first.decisions), {"classic", "modern"})
        self.assertTrue(first.decision_for("classic").reduced)
        self.assertEqual(first.decision_for("modern"), first.decision_for("classic"))

        repeated = self.contract.update(system=REDUCE)
        self.assertEqual(repeated.changed, ())
        self.assertEqual(repeated.decisions, first.decisions)

        relaxed = self.contract.update(system=FULL, user=FULL)
        self.assertEqual(relaxed.changed, ("classic", "modern"))
        self.assertTrue(relaxed.decision_for("classic").motion_allowed)

    def test_per_presentation_override_diverges_from_shared_state(self):
        self.contract.register("classic")
        self.contract.register("modern")
        result = self.contract.update(
            system=FULL,
            presentations={"classic": REDUCE, "modern": FULL},
        )
        classic = result.decision_for("classic")
        modern = result.decision_for("modern")
        self.assertTrue(classic.reduced)
        self.assertEqual(classic.source, PRESENTATION)
        self.assertEqual(classic.conflicts, (SYSTEM,))
        self.assertTrue(modern.motion_allowed)
        self.assertEqual(self.contract.snapshot()["classic"], classic)

    def test_late_registration_uses_current_inputs_and_unregister_cleans_up(self):
        self.contract.register("classic")
        self.contract.update(system=REDUCE, user=FULL,
                             presentations={"classic": REDUCE})
        self.contract.register("modern")
        self.assertTrue(self.contract.snapshot()["modern"].reduced)
        self.assertEqual(self.contract.snapshot()["modern"].source, SYSTEM)
        self.assertEqual(self.contract.snapshot()["modern"].conflicts, (USER,))

        self.assertTrue(self.contract.unregister("classic"))
        self.assertFalse(self.contract.unregister("classic"))
        self.assertNotIn("classic", self.contract.snapshot())
        with self.assertRaises(MotionContractError):
            self.contract.update(system=REDUCE,
                                 presentations={"classic": REDUCE})

    def test_snapshot_and_result_decisions_are_immutable(self):
        self.contract.register("classic")
        result = self.contract.update(system=REDUCE)
        with self.assertRaises(TypeError):
            result.decisions["classic"] = resolve(FULL)
        with self.assertRaises(TypeError):
            self.contract.snapshot()["classic"] = resolve(FULL)
        with self.assertRaises(MotionContractError):
            result.decision_for("missing")

    def test_bounds_and_invalid_registration_fail_closed(self):
        for bad in ("", "Classic", "bad name", "a" * 65, None, 7, "a/b"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(MotionContractError):
                    self.contract.register(bad)
                with self.assertRaises(MotionContractError):
                    self.contract.unregister(bad)
        self.contract.register("classic")
        with self.assertRaises(MotionContractError):
            self.contract.register("classic")
        for index in range(MAX_CONSUMERS - 1):
            self.contract.register("pack" + str(index))
        with self.assertRaisesRegex(MotionContractError, "limit"):
            self.contract.register("overflow")

        self.contract.clear()
        self.contract.register("classic")
        with self.assertRaises(MotionContractError):
            self.contract.update(system="maybe")
        with self.assertRaises(MotionContractError):
            self.contract.update(presentations=["classic"])
        too_many = {"pack" + str(i): UNSET for i in range(MAX_PRESENTATIONS + 1)}
        with self.assertRaisesRegex(MotionContractError, "limit"):
            self.contract.update(presentations=too_many)

    def test_clear_releases_state(self):
        self.contract.register("classic")
        self.contract.update(system=REDUCE)
        self.contract.clear()
        self.assertEqual(self.contract.version, 0)
        self.assertEqual(self.contract.consumer_ids, ())
        self.assertEqual(dict(self.contract.snapshot()), {})
        self.contract.register("classic")
        self.assertTrue(self.contract.update().decision_for("classic").from_default)


class ScopeTests(unittest.TestCase):
    def test_no_rendering_polling_threads_or_network(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/accessibility/reduced_motion_contract.py").read_text()
        for forbidden in ("import PySide", "import PyQt", "import socket",
                          "import subprocess", "import threading",
                          "from threading", "import time", "import asyncio",
                          "import importlib", "QTimer(", "time.sleep(",
                          "open("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
