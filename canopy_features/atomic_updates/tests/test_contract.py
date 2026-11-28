"""Regression tests for the read-only atomic-update transaction contract."""
from __future__ import annotations

import re
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from canopy_features.atomic_updates import contract as c

DIGEST_A = "1" * 64
DIGEST_B = "2" * 64
STAMP = "2026-11-28T00:00:00Z"
SOURCE_DIR = Path(__file__).resolve().parents[1]


def observation(**changes: object) -> c.DeploymentObservation:
    values: dict[str, object] = {
        "deployment_id": "dep-current",
        "commit_digest": DIGEST_A,
        "staged_digest": DIGEST_B,
        "version": "42.20261128.0",
        "booted": True,
        "signature_state": "VERIFIED",
        "core_writable": False,
        "retained": True,
        "observed_at": STAMP,
    }
    values.update(changes)
    return c.DeploymentObservation(**values)  # type: ignore[arg-type]


def candidate(**changes: object) -> c.UpdateCandidate:
    values: dict[str, object] = {
        "target_digest": DIGEST_B,
        "version": "43.20261205.0",
        "signature_state": "VERIFIED",
        "origin": "synthetic-kinoite-image",
        "size_bytes": 1024,
    }
    values.update(changes)
    return c.UpdateCandidate(**values)  # type: ignore[arg-type]


def checkpoint(**changes: object) -> c.Checkpoint:
    values: dict[str, object] = {
        "deployment_id": "dep-current",
        "commit_digest": DIGEST_A,
        "pinned": True,
        "created_at": STAMP,
    }
    values.update(changes)
    return c.Checkpoint(**values)  # type: ignore[arg-type]


def gates(**changes: object) -> c.VerificationGates:
    values: dict[str, object] = {
        "signature_ok": True,
        "digest_match": True,
        "checkpoint_retained": True,
        "core_immutable": True,
        "no_layered_mutation": True,
        "within_bounds": True,
        "activation_deferred": True,
        "stock_plasma_fallback": True,
    }
    values.update(changes)
    return c.VerificationGates(**values)  # type: ignore[arg-type]


def decide(**changes: object) -> c.TransactionDecision:
    values: dict[str, object] = {
        "observation": observation(),
        "candidate": candidate(),
        "checkpoint": checkpoint(),
        "gates": gates(),
        "confirm_ok": True,
    }
    values.update(changes)
    return c.plan_update(
        values["observation"],  # type: ignore[arg-type]
        values["candidate"],  # type: ignore[arg-type]
        values["checkpoint"],  # type: ignore[arg-type]
        values["gates"],  # type: ignore[arg-type]
        confirm_ok=values["confirm_ok"],  # type: ignore[arg-type]
    )


class ContractTests(unittest.TestCase):
    def test_ready_handoff_has_bounded_inert_steps(self) -> None:
        decision = decide()
        self.assertEqual(decision.status, c.STATUS_READY)
        self.assertEqual(decision.reasons, (c.REASON_OK,))
        self.assertEqual(decision.phase, c.PHASE_HANDOFF)
        self.assertEqual(len(decision.steps), 6)
        self.assertTrue(all(type(step) is c.HandoffStep for step in decision.steps))
        self.assertTrue(all(not step.executed for step in decision.steps))
        self.assertTrue(all(step.interface in c.INTERFACES.values() for step in decision.steps))
        self.assertEqual(decision.steps[0].phase, c.PHASE_PRECHECK)
        self.assertEqual(decision.steps[-1].phase, c.PHASE_CONFIRM)

    def test_decision_never_claims_real_guest_or_execution(self) -> None:
        decision = decide()
        self.assertEqual(decision.synthetic_label, c.SYNTHETIC_LABEL)
        self.assertIn(decision.guest_status, (c.GUEST_BLOCKED, c.GUEST_NOT_RUN))
        self.assertFalse(any(step.executed for step in decision.steps))
        self.assertFalse(any("sudo" in step.detail or "rpm-ostree " in step.detail for step in decision.steps))

    def test_unsigned_candidate_blocks(self) -> None:
        decision = decide(candidate=candidate(signature_state="UNVERIFIED"), gates=gates(signature_ok=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_UNSIGNED, decision.reasons)
        self.assertEqual(decision.steps, ())

    def test_digest_mismatch_blocks(self) -> None:
        decision = decide(observation=observation(staged_digest="3" * 64))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_DIGEST_MISMATCH, decision.reasons)

    def test_missing_staged_digest_blocks(self) -> None:
        decision = decide(observation=observation(staged_digest=None))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_DIGEST_MISMATCH, decision.reasons)

    def test_writable_core_is_forbidden(self) -> None:
        decision = decide(observation=observation(core_writable=True), gates=gates(core_immutable=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_CORE_MUTATION, decision.reasons)

    def test_layered_core_mutation_is_forbidden(self) -> None:
        decision = decide(gates=gates(no_layered_mutation=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_LAYERED_MUTATION, decision.reasons)

    def test_missing_checkpoint_blocks(self) -> None:
        decision = decide(checkpoint=checkpoint(pinned=False, commit_digest="4" * 64),
                          gates=gates(checkpoint_retained=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_CHECKPOINT_MISSING, decision.reasons)
        self.assertIn(c.REASON_CHECKPOINT_DIGEST_MISMATCH, decision.reasons)

    def test_unretained_booted_deployment_blocks(self) -> None:
        decision = decide(observation=observation(retained=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_CHECKPOINT_MISSING, decision.reasons)

    def test_unbounded_candidate_blocks(self) -> None:
        decision = decide(candidate=candidate(size_bytes=c.MAX_CANDIDATE_BYTES + 1),
                          gates=gates(within_bounds=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_UNBOUNDED, decision.reasons)

    def test_immediate_activation_blocks(self) -> None:
        decision = decide(gates=gates(activation_deferred=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_ACTIVATION_NOT_DEFERRED, decision.reasons)

    def test_missing_stock_fallback_blocks(self) -> None:
        decision = decide(gates=gates(stock_plasma_fallback=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_NO_FALLBACK, decision.reasons)

    def test_confirm_failure_describes_rollback_only(self) -> None:
        decision = decide(confirm_ok=False)
        self.assertEqual(decision.status, c.STATUS_ROLLBACK)
        self.assertEqual(decision.phase, c.PHASE_ROLLBACK)
        self.assertEqual(decision.reasons, (c.REASON_CONFIRM_FAILED,))
        self.assertEqual(len(decision.steps), 1)
        self.assertEqual(decision.steps[0].interface, c.INTERFACES["rollback"])
        self.assertTrue(decision.steps[0].requires_reboot)
        self.assertFalse(decision.steps[0].executed)

    def test_rollback_without_checkpoint_blocks(self) -> None:
        decision = c.plan_rollback(observation(), checkpoint(pinned=False))
        self.assertEqual(decision.status, c.STATUS_BLOCKED)
        self.assertIn(c.REASON_CHECKPOINT_MISSING, decision.reasons)
        self.assertEqual(decision.steps, ())

    def test_hostile_types_fail_closed(self) -> None:
        cases = (
            {"size_bytes": True},
            {"size_bytes": [1]},
            {"size_bytes": "1024"},
            {"version": 42},
            {"version": ["v1"]},
            {"signature_state": object()},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(c.AtomicUpdatesError):
                    candidate(**changes)
        for changes in ({"core_writable": 1}, {"booted": "true"}, {"retained": []}):
            with self.subTest(changes=changes):
                with self.assertRaises(c.AtomicUpdatesError):
                    observation(**changes)

    def test_control_characters_rejected(self) -> None:
        with self.assertRaises(c.AtomicUpdatesError):
            candidate(origin="synthetic\nrpm-ostree upgrade")
        with self.assertRaises(c.AtomicUpdatesError):
            observation(version="42\u200b")

    def test_bad_digest_shape_rejected(self) -> None:
        with self.assertRaises(c.AtomicUpdatesError):
            candidate(target_digest="ABC" * 21 + "AB")
        with self.assertRaises(c.AtomicUpdatesError):
            checkpoint(commit_digest="f" * 63)

    def test_decision_and_steps_are_immutable(self) -> None:
        decision = decide()
        with self.assertRaises(FrozenInstanceError):
            decision.status = c.STATUS_BLOCKED  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            decision.steps[0].executed = True  # type: ignore[misc]

    def test_executed_step_cannot_be_constructed(self) -> None:
        with self.assertRaises(c.AtomicUpdatesError):
            c.HandoffStep(c.PHASE_HANDOFF, c.INTERFACES["deploy"], "x", executed=True)

    def test_wrong_record_types_rejected(self) -> None:
        with self.assertRaises(c.AtomicUpdatesError):
            c.plan_update(object(), candidate(), checkpoint(), gates(), confirm_ok=True)  # type: ignore[arg-type]

    def test_core_modules_import_no_host_io(self) -> None:
        forbidden = re.compile(r"\b(?:import|from)\s+(?:os|sys|subprocess|socket|shutil|pathlib|ctypes|tempfile)\b")
        for name in ("contract.py", "fixture.py"):
            text = (SOURCE_DIR / name).read_text(encoding="utf-8")
            self.assertIsNone(forbidden.search(text), f"{name} imports host I/O")
            self.assertNotIn("rpm-ostree ", text)
            self.assertNotIn("sudo", text)

    def test_reasons_are_stable_tokens(self) -> None:
        pattern = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
        for reason in c.REASONS:
            self.assertRegex(reason, pattern)
        self.assertTrue(c.REASONS.issuperset(decide(gates=gates(stock_plasma_fallback=False)).reasons))


if __name__ == "__main__":
    unittest.main()
