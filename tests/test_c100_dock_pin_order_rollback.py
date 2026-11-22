"""Offline pin-order transaction tests: in-memory journals, no Qt or Mint runtime.

Partially written state and conflict recovery are exercised explicitly.
"""

from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import unittest

from canopy_features.dock.pin_order_rollback import (
    MAX_JOURNAL_BYTES, PHASES, PinOrderError, Transaction,
    decode, encode, new_transaction, plan_recovery, with_phase,
)

BEFORE = ("files", "browser", "settings", "photos")
AFTER = ("browser", "files", "settings", "photos")


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.transaction = new_transaction("tx-001", BEFORE, AFTER)
        self.raw = encode(self.transaction)

    def test_round_trip_and_immutable_record(self):
        restored = decode(self.raw)
        self.assertEqual(restored, self.transaction)
        self.assertIsInstance(restored.before, tuple)
        self.assertIsInstance(restored.after, tuple)
        with self.assertRaises(FrozenInstanceError):
            restored.phase = "committed"

    def test_all_phases_round_trip(self):
        for phase in PHASES:
            with self.subTest(phase=phase):
                record = with_phase(self.transaction, phase)
                self.assertEqual(decode(encode(record)), record)

    def test_canonical_bytes_are_platform_independent(self):
        canonical = (b'{"after":["browser","files","settings","photos"],'
                     b'"before":["files","browser","settings","photos"],'
                     b'"phase":"prepared","transaction_id":"tx-001","version":1}')
        expected_sum = "sha256:" + hashlib.sha256(canonical).hexdigest()
        expected = (b'{"after":["browser","files","settings","photos"],'
                    b'"before":["files","browser","settings","photos"],'
                    b'"checksum":"' + expected_sum.encode("ascii") + b'",'
                    b'"phase":"prepared","transaction_id":"tx-001","version":1}')
        self.assertEqual(self.raw, expected)

    def test_truncated_journal_is_detected(self):
        for cut in (1, 10, len(self.raw) // 2, len(self.raw) - 1):
            with self.subTest(cut=cut):
                with self.assertRaisesRegex(PinOrderError, "truncated|corrupt"):
                    decode(self.raw[:cut])

    def test_checksum_mismatch_detected_after_partial_rewrite(self):
        payload = json.loads(self.raw)
        payload["after"] = ["browser", "photos", "settings", "files"]
        tampered = json.dumps(payload, sort_keys=True,
                              separators=(",", ":")).encode("ascii")
        with self.assertRaisesRegex(PinOrderError, "checksum mismatch"):
            decode(tampered)

    def test_bad_structure_and_bounds_rejected(self):
        payload = json.loads(self.raw)
        cases = {}
        extra = dict(payload)
        extra["surprise"] = 1
        cases["extra field"] = extra
        missing = dict(payload)
        del missing["before"]
        cases["missing field"] = missing
        cases["wrong root"] = []
        cases["array pins"] = dict(payload, before="files,browser")
        cases["bad version"] = dict(payload, version=2)
        cases["bool version"] = dict(payload, version=True)
        cases["bad checksum"] = dict(payload, checksum="nope")
        for label, bad in cases.items():
            with self.subTest(label=label):
                raw = json.dumps(bad, sort_keys=True,
                                 separators=(",", ":")).encode("ascii")
                with self.assertRaises(PinOrderError):
                    decode(raw)

    def test_oversized_journal_rejected_before_parse(self):
        with self.assertRaisesRegex(PinOrderError, "size bound"):
            decode(b"{" * (MAX_JOURNAL_BYTES + 1))

    def test_invalid_pins_duplicates_and_changed_set_rejected(self):
        with self.assertRaises(PinOrderError):
            new_transaction("tx-002", ["files", "files"], AFTER)
        with self.assertRaises(PinOrderError):
            new_transaction("tx-002", ["files", "bad id!"], AFTER)
        with self.assertRaises(PinOrderError):
            new_transaction("tx-002", BEFORE, ["browser", "files", "mail", "photos"])
        with self.assertRaises(PinOrderError):
            new_transaction("BAD ID", BEFORE, AFTER)
        with self.assertRaises(PinOrderError):
            with_phase(self.transaction, "unknown")

    def test_rejects_unbounded_pin_lists(self):
        pins = ["pin-%03d" % i for i in range(65)]
        with self.assertRaisesRegex(PinOrderError, "pin bound"):
            new_transaction("tx-003", pins, list(reversed(pins)))

    def test_module_has_no_polling_or_os_side_effects(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/dock/pin_order_rollback.py").read_text()
        for forbidden in ("QTimer", "time.sleep", "Thread(", "socket",
                          "subprocess", "open(", "import os", "asyncio"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.transaction = new_transaction("tx-001", BEFORE, AFTER)

    def plan(self, phase, current, baseline=BEFORE):
        raw = encode(with_phase(self.transaction, phase))
        return plan_recovery(raw, current, baseline)

    def test_no_journal_is_clean(self):
        plan = plan_recovery(None, BEFORE, BEFORE)
        self.assertEqual(plan.status, "CLEAN")
        self.assertFalse(plan.should_write_order)
        self.assertTrue(plan.should_clear_journal)

    def test_partially_written_journal_at_baseline_discards_safely(self):
        raw = encode(self.transaction)
        plan = plan_recovery(raw[:len(raw) // 2], BEFORE, BEFORE)
        self.assertEqual(plan.status, "DISCARD")
        self.assertEqual(plan.order, ())
        self.assertFalse(plan.should_write_order)
        self.assertTrue(plan.should_clear_journal)

    def test_partially_written_journal_with_diverged_state_fails_closed(self):
        raw = encode(self.transaction)
        plan = plan_recovery(raw[:len(raw) // 2], AFTER, BEFORE)
        self.assertEqual(plan.status, "INVALID")
        self.assertEqual(plan.order, ())
        self.assertFalse(plan.should_write_order)
        self.assertFalse(plan.should_clear_journal)

    def test_prepared_applied_but_uncommitted_reverts(self):
        plan = self.plan("prepared", AFTER)
        self.assertEqual(plan.status, "REVERT")
        self.assertEqual(plan.order, BEFORE)
        self.assertTrue(plan.should_write_order)

    def test_prepared_never_applied_discards(self):
        plan = self.plan("prepared", BEFORE)
        self.assertEqual(plan.status, "DISCARD")
        self.assertFalse(plan.should_write_order)

    def test_committed_state_matches_discards(self):
        plan = self.plan("committed", AFTER)
        self.assertEqual(plan.status, "DISCARD")
        self.assertFalse(plan.should_write_order)

    def test_committed_marker_without_applied_order_reapplies(self):
        plan = self.plan("committed", BEFORE)
        self.assertEqual(plan.status, "APPLY")
        self.assertEqual(plan.order, AFTER)
        self.assertTrue(plan.should_write_order)

    def test_reverted_marker_without_applied_revert_repeats_revert(self):
        plan = self.plan("reverted", AFTER)
        self.assertEqual(plan.status, "REVERT")
        self.assertEqual(plan.order, BEFORE)

    def test_reverted_state_matches_discards(self):
        plan = self.plan("reverted", BEFORE)
        self.assertEqual(plan.status, "DISCARD")

    def test_conflicting_state_fails_closed_for_every_phase(self):
        foreign = ("files", "settings", "browser", "photos")
        unknown_pin = ("files", "browser", "mail", "photos")
        for phase in PHASES:
            for current in (foreign, unknown_pin, ()):
                with self.subTest(phase=phase, current=current):
                    plan = self.plan(phase, current)
                    self.assertEqual(plan.status, "CONFLICT")
                    self.assertEqual(plan.order, ())
                    self.assertFalse(plan.should_write_order)
                    self.assertFalse(plan.should_clear_journal)

    def test_invalid_current_or_baseline_rejected(self):
        with self.assertRaises(PinOrderError):
            plan_recovery(None, ["files", "files"], BEFORE)
        with self.assertRaises(PinOrderError):
            plan_recovery(None, BEFORE, ["bad id!"])
        with self.assertRaises(TypeError):
            plan_recovery(123, BEFORE, BEFORE)


if __name__ == "__main__":
    unittest.main()
