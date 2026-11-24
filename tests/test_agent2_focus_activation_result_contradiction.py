"""Regression tests for contradictory activation results in focus intents.

Offline/in-memory only: no Qt, compositor, host focus call or Mint claim.
"""
import unittest

from canopy_features.windows.focus_intents import (
    ACTIVATION_FAILED, GRANTED, FocusBroker, FocusIntent,
)


class ActivationResultContractTests(unittest.TestCase):
    """An ambiguous backend result must not be reported as focus actuated."""

    @staticmethod
    def _decision(result, window_id=42):
        # Finite, bounded inputs only; no unbounded iterable in a RED test.
        broker = FocusBroker(lambda origin, target: True,
                             lambda wid, r=result: r)
        ref = broker.register_window("app.target", window_id)
        return broker.request_focus(FocusIntent("app.origin", ref))

    def test_non_boolean_activation_result_is_not_a_grant(self):
        ambiguous = (0, 1, -1, "refused", "", "ok", [], (), {}, object(), -0.0)
        for result in ambiguous:
            with self.subTest(result_type=type(result).__name__):
                decision = self._decision(result)
                self.assertEqual(decision.status, ACTIVATION_FAILED)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "activation result not boolean")

    def test_explicit_false_is_still_activation_refused(self):
        decision = self._decision(False)
        self.assertEqual(decision.status, ACTIVATION_FAILED)
        self.assertEqual(decision.reason, "activation refused")

    def test_none_and_true_activation_results_still_grant(self):
        for result in (None, True):
            with self.subTest(result=result):
                decision = self._decision(result)
                self.assertEqual(decision.status, GRANTED)
                self.assertTrue(decision.allowed)
                self.assertEqual(decision.reason, "")


if __name__ == "__main__":
    unittest.main()
