"""Tests for the bounded, immutable host-facing recovery-readiness snapshot."""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.reliability import event_delivery_loss as delivery
from canopy_features.reliability import lock_session_events as lock
from canopy_features.reliability import startup_checkpoints as checkpoints


def _m():
    from canopy_features.reliability import recovery_readiness_snapshot as module
    return module


def _plain(value):
    if isinstance(value, MappingProxyType):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _encode(record):
    return json.dumps(_plain(record.to_dict()), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _startup():
    return checkpoints.RecoveryDecision(
        checkpoints.READY, ("shell", "dock"), (), None,
        "all startup steps are durable")


def _session():
    return lock.Reconciler(initial_locked=False)


def _channel():
    channel = delivery.BoundedDeliveryChannel(
        capacity=4, policy="drop_oldest", start_sequence=1)
    channel.send(1, "a")
    channel.send(2, "b")
    channel.receive()
    channel.receive()
    return channel


def _compose_clean():
    channel = _channel()
    return _m().compose(_startup(), _session(), channel.stats,
                        channel.overflow_notices())


class RecoveryReadinessSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        m = _m()
        self.assertIsInstance(record, m.RecoveryReadinessSnapshot)
        self.assertEqual(record.schema, m.SCHEMA)
        self.assertEqual(record.startup.action, checkpoints.READY)
        self.assertTrue(record.startup.safe_to_start)
        self.assertEqual(record.startup.completed_count, 2)
        self.assertEqual(record.session.label, "active")
        self.assertEqual(record.session.accepted, 0)
        self.assertEqual(record.delivery.sent, 2)
        self.assertEqual(record.delivery.delivered, 2)
        self.assertEqual(record.delivery.notice_count, 0)
        self.assertIsNone(record.delivery.last_policy)
        self.assertEqual(record.status, m.STATUS_OK)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        for target, field in ((record, "status"), (record.startup, "reason"),
                              (record.session, "recent_statuses"),
                              (record.delivery, "notice_count")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_is_fresh_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        again = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertIsNot(view, again)
        for key in ("startup", "session", "delivery"):
            self.assertIsNot(view[key], again[key])
        with self.assertRaises(TypeError):
            view["status"] = "tampered"
        with self.assertRaises(TypeError):
            view["delivery"]["sent"] = 99

    def test_to_dict_key_order_is_fixed(self):
        view = _compose_clean().to_dict()
        self.assertEqual(tuple(view), (
            "schema", "status", "acceptance", "observation",
            "startup", "session", "delivery"))
        self.assertEqual(tuple(view["startup"]), (
            "action", "safe_to_start", "needs_rollback", "completed_count",
            "unwind_count", "reason"))
        self.assertEqual(tuple(view["session"]), (
            "label", "suspended", "locked", "accepted", "recent_statuses"))
        self.assertEqual(tuple(view["delivery"]), (
            "sent", "received", "delivered", "duplicates", "reordered",
            "gaps", "missed", "dropped", "rejected", "notice_count",
            "last_policy"))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))

    def test_notice_history_is_bounded(self):
        channel = delivery.BoundedDeliveryChannel(
            capacity=16, policy="reject_new", start_sequence=1)
        for seq in range(1, 40):
            channel.send(seq, "p")
        self.assertGreater(len(channel.overflow_notices()), _m().MAX_NOTICES)
        record = _m().compose(_startup(), _session(), channel.stats,
                              channel.overflow_notices())
        self.assertEqual(record.delivery.notice_count, _m().MAX_NOTICES)
        self.assertEqual(record.delivery.last_policy, "reject_new")

    def test_session_history_is_bounded(self):
        session = lock.Reconciler(initial_locked=False, history_limit=32)
        for tick in range(20):
            session.observe(lock.SessionEvent(
                lock.LOCK if tick % 2 == 0 else lock.UNLOCK, float(tick + 1)))
        record = _m().compose(_startup(), session, _channel().stats)
        self.assertEqual(len(session.history), 20)
        self.assertEqual(len(record.session.recent_statuses), _m().MAX_RECENT)

    def test_long_reason_is_bounded(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, (), (), None, "x" * 500)
        record = _m().compose(decision, _session(), _channel().stats)
        self.assertEqual(record.startup.reason, "x" * _m().MAX_CHARS)

    def test_status_blocked_for_fail_closed_startup(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.FAIL_CLOSED, (), ("a",), None, "unsafe")
        record = _m().compose(decision, _session(), _channel().stats)
        self.assertEqual(record.status, _m().STATUS_BLOCKED)
        self.assertTrue(record.is_blocked)

    def test_status_attention_for_locked_session(self):
        session = lock.Reconciler(initial_locked=True)
        record = _m().compose(_startup(), session, _channel().stats)
        self.assertEqual(record.status, _m().STATUS_ATTENTION)

    def test_status_attention_for_delivery_anomaly(self):
        channel = delivery.BoundedDeliveryChannel(
            capacity=4, policy="drop_oldest", start_sequence=1)
        for seq in range(1, 8):
            channel.send(seq, "p")
        record = _m().compose(_startup(), _session(), channel.stats,
                              channel.overflow_notices())
        self.assertEqual(record.status, _m().STATUS_ATTENTION)

    def test_fixed_negative_claims_under_adversarial_input(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.ROLLBACK, (), (), None, "ACCEPTED PASS MINT")
        record = _m().compose(decision, _session(), _channel().stats)
        self.assertEqual(record.acceptance, _m().ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.observation, _m().OBSERVATION_NOT_PERFORMED)

    def test_fail_closed_wrong_components(self):
        for args in ((None, _session(), _channel().stats),
                     (_startup(), None, _channel().stats),
                     (_startup(), _session(), None),
                     (_startup(), _session(), _channel().stats, (object(),))):
            with self.subTest(args=len(args)):
                with self.assertRaises(_m().SnapshotError):
                    _m().compose(*args)

    def test_fail_closed_unknown_recovery_action(self):
        decision = checkpoints.RecoveryDecision(
            "FORGED", (), (), None, "reason")
        with self.assertRaises(_m().SnapshotError):
            _m().compose(decision, _session(), _channel().stats)

    def test_fail_closed_inconsistent_session_label(self):
        session = lock.Reconciler(initial_locked=False)
        object.__setattr__(session, "_state", None)
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_startup(), session, _channel().stats)

    def test_cross_call_independence_no_mutable_alias(self):
        session = lock.Reconciler(initial_locked=False)
        channel = _channel()
        record = _m().compose(_startup(), session, channel.stats,
                              channel.overflow_notices())
        before = _encode(record)
        session.observe(lock.SessionEvent(lock.LOCK, 1.0))
        channel.send(99, "late")
        self.assertEqual(_encode(record), before)
        view = record.to_dict()
        self.assertIsInstance(view["session"]["recent_statuses"], tuple)
        self.assertIsInstance(view["startup"]["reason"], str)

    def test_no_partial_record_on_rejection(self):
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_startup(), _session(), _channel().stats,
                         (delivery.OverflowNotice(1, "drop_oldest", 0),
                          object()))

    def test_purity_ast(self):
        source = Path(_m().__file__).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0]
                               for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"os", "sys", "socket", "subprocess", "threading",
                     "time", "datetime", "random", "asyncio", "PySide6",
                     "PyQt6"}
        self.assertFalse(imports & forbidden)


if __name__ == "__main__":
    unittest.main()
