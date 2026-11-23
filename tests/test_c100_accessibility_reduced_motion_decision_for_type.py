"""Regression: PropagationResult.decision_for must fail closed on unhashable ids.

The documented contract is MotionContractError("unknown reduced-motion
consumer") for any id that is not a delivered consumer. A bare TypeError from
a dict/MappingProxy lookup is not part of that boundary and must not escape.
Pure offline model tests; no Qt, desktop, Mint or rendering claims.
"""
import unittest

from canopy_features.accessibility.reduced_motion_contract import (
    MotionContractError,
    ReducedMotionContract,
    resolve,
)


class DecisionForTypeTests(unittest.TestCase):
    def setUp(self):
        self.contract = ReducedMotionContract()
        self.contract.register("classic")
        self.contract.register("modern")
        self.result = self.contract.update(system="reduce")

    def test_unhashable_consumer_id_raises_domain_error(self):
        for bad in ([], {}, ["classic"], {"classic": 1}, {1, 2}):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(MotionContractError) as ctx:
                    self.result.decision_for(bad)
                self.assertEqual(str(ctx.exception),
                                 "unknown reduced-motion consumer")

    def test_hashable_unknown_id_still_raises_domain_error(self):
        for bad in (None, 7, 3.5, True, b"classic", "missing"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(MotionContractError):
                    self.result.decision_for(bad)

    def test_known_consumer_id_returns_the_delivered_decision(self):
        self.assertEqual(self.result.decision_for("classic"), resolve("reduce"))
        self.assertEqual(self.result.decision_for("modern"),
                         self.result.decision_for("classic"))

    def test_error_is_a_value_error_not_a_bare_type_error(self):
        # MotionContractError subclasses ValueError; a raw TypeError from the
        # mapping lookup would fail this isinstance check.
        with self.assertRaises(ValueError):
            self.result.decision_for([])


if __name__ == "__main__":
    unittest.main()
