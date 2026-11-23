"""Wrong-type resource batches must fail closed in the theme rollback ledger.

The public ``prepare`` contract documents ``INVALID_RESOURCES`` for any
batch that is not an iterable of non-empty strings. A non-iterable batch
used to leak ``TypeError`` from the private normalizer instead. No Qt,
compositor, Mint session or compiled binary is involved here.
"""

import unittest

from canopy_features.reliability.theme_transition_rollback import (
    IDLE,
    ThemeTransitionRollback,
)


class ThemeRollbackResourceTypeTests(unittest.TestCase):
    def make_ledger(self):
        return ThemeTransitionRollback("classic", ("theme.qml",))

    def test_prepare_rejects_none_resources_with_documented_status(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.prepare("modern", None), "INVALID_RESOURCES")
        snap = ledger.snapshot()
        self.assertEqual(snap.state, IDLE)
        self.assertEqual(snap.active, "classic")
        self.assertIsNone(snap.candidate)
        self.assertEqual(snap.live_resources, {"theme.qml"})
        self.assertEqual(snap.abandoned_resources, frozenset())

    def test_prepare_rejects_non_iterable_scalar_resources(self):
        for batch in (7, 3.5, True, object()):
            with self.subTest(batch=type(batch).__name__):
                ledger = self.make_ledger()
                self.assertEqual(ledger.prepare("modern", batch),
                                 "INVALID_RESOURCES")
                self.assertEqual(ledger.snapshot().state, IDLE)

    def test_rejected_batch_leaves_ledger_retryable(self):
        ledger = self.make_ledger()
        for batch in (None, 7):
            with self.subTest(batch=batch):
                self.assertEqual(ledger.prepare("modern", batch),
                                 "INVALID_RESOURCES")
        self.assertEqual(ledger.prepare("modern", ("modern.qml",)), "PREPARED")
        self.assertEqual(ledger.commit(), "COMMITTED")
        self.assertEqual(ledger.snapshot().active, "modern")

    def test_valid_iterables_and_generator_batches_still_work(self):
        cases = (
            {"modern.qml"},
            ("modern.qml",),
            ["modern.qml"],
            (name for name in ("modern.qml",)),
        )
        for batch in cases:
            with self.subTest(batch=type(batch).__name__):
                ledger = self.make_ledger()
                self.assertEqual(ledger.prepare("modern", batch), "PREPARED")
                self.assertEqual(ledger.snapshot().live_resources,
                                 {"theme.qml", "modern.qml"})

    def test_other_invalid_resource_shapes_keep_existing_status(self):
        for batch in ([""], [1], ["a.qml", "a.qml"], [["nested"]]):
            with self.subTest(batch=repr(batch)):
                ledger = self.make_ledger()
                self.assertEqual(ledger.prepare("modern", batch),
                                 "INVALID_RESOURCES")

    def test_invalid_theme_precedes_resource_validation(self):
        ledger = self.make_ledger()
        self.assertEqual(ledger.prepare("", None), "INVALID_THEME")
        self.assertEqual(ledger.snapshot().state, IDLE)

    def test_constructor_contract_unchanged(self):
        with self.assertRaises(TypeError):
            ThemeTransitionRollback(7, ("theme.qml",))
        with self.assertRaises(ValueError):
            ThemeTransitionRollback("classic", ("a", "a"))
        ledger = ThemeTransitionRollback("classic", ("theme.qml",))
        self.assertEqual(ledger.snapshot().active, "classic")


if __name__ == "__main__":
    unittest.main()
