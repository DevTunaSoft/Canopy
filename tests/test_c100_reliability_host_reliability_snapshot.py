"""Tests for the bounded, immutable host-facing reliability snapshot.

The snapshot composes the already-tested value objects from
``startup_checkpoints``, ``event_delivery_loss`` and ``switcher_state`` into
one deterministic, host-facing record. These tests pin the contract: pure
composition, bounded embedded collections, immutable views, deterministic
bytes, explicit status derivation and fail-closed input validation.
"""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.reliability import event_delivery_loss as delivery
from canopy_features.reliability import startup_checkpoints as checkpoints
from canopy_features.reliability import host_reliability_snapshot as snapshot
from canopy_features.windows import switcher_state as switcher


def _plain(value):
    """Recursively turn MappingProxyType views into plain dicts for JSON."""
    if isinstance(value, MappingProxyType):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _clean_startup():
    return checkpoints.RecoveryDecision(
        checkpoints.READY, ("shell", "dock"), (), None,
        "all startup steps are durable")


def _clean_delivery():
    channel = delivery.BoundedDeliveryChannel(
        capacity=4, policy="drop_oldest", start_sequence=1)
    channel.send(1, "a")
    channel.send(2, "b")
    channel.receive()
    channel.receive()
    return channel


def _clean_switcher():
    state = switcher.SwitcherState([10, 20, 30], current=10)
    state.begin()
    state.next()
    return state.snapshot()


def _compose_clean():
    channel = _clean_delivery()
    return snapshot.compose(
        _clean_startup(), channel.stats, channel.overflow_notices(),
        _clean_switcher())


class HostReliabilitySnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        self.assertIsInstance(record, snapshot.HostReliabilitySnapshot)
        self.assertEqual(record.schema, snapshot.SCHEMA)
        self.assertEqual(record.startup.action, checkpoints.READY)
        self.assertTrue(record.startup.safe_to_start)
        self.assertEqual(record.startup.completed_count, 2)
        self.assertEqual(record.delivery.sent, 2)
        self.assertEqual(record.delivery.delivered, 2)
        self.assertEqual(record.delivery.notice_count, 0)
        self.assertIsNone(record.delivery.last_policy)
        self.assertTrue(record.switcher.active)
        self.assertEqual(record.switcher.current, 10)
        self.assertEqual(record.switcher.selected, 20)
        self.assertEqual(record.switcher.window_count, 3)
        self.assertEqual(record.switcher.order, (10, 20, 30))
        self.assertEqual(record.status, snapshot.STATUS_OK)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        with self.assertRaises(FrozenInstanceError):
            record.status = snapshot.STATUS_BLOCKED
        with self.assertRaises(FrozenInstanceError):
            record.delivery.sent = 99
        with self.assertRaises(FrozenInstanceError):
            record.switcher.order = ()

    def test_to_dict_is_a_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        with self.assertRaises(TypeError):
            view["status"] = "tampered"
        with self.assertRaises(TypeError):
            view["delivery"]["sent"] = 99
        self.assertEqual(view["switcher"]["order"], (10, 20, 30))

    def test_deterministic_bytes_for_equal_inputs(self):
        first = _plain(_compose_clean().to_dict())
        second = _plain(_compose_clean().to_dict())
        encode = lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(encode(first), encode(second))
        self.assertIn(b'"schema":1', encode(first))

    def test_notice_history_is_bounded_to_last_entries(self):
        # The channel bounds its own notice history by capacity, so use a
        # capacity above MAX_NOTICES to make the snapshot's tighter cap visible.
        channel = delivery.BoundedDeliveryChannel(
            capacity=16, policy="reject_new", start_sequence=1)
        for seq in range(1, 30):
            channel.send(seq, "p")
        self.assertGreater(len(channel.overflow_notices()), snapshot.MAX_NOTICES)
        record = snapshot.compose(
            _clean_startup(), channel.stats, channel.overflow_notices(),
            _clean_switcher())
        self.assertEqual(record.delivery.notice_count, snapshot.MAX_NOTICES)
        self.assertEqual(record.delivery.last_policy, "reject_new")
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_blocked_on_rollback(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.ROLLBACK, ("shell",), ("shell",), "shell",
            "partial startup; unwind durable steps")
        channel = _clean_delivery()
        record = snapshot.compose(
            decision, channel.stats, channel.overflow_notices(),
            _clean_switcher())
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)
        self.assertTrue(record.is_blocked)
        self.assertFalse(record.startup.safe_to_start)
        self.assertEqual(record.startup.unwind_count, 1)

    def test_status_blocked_on_fail_closed(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.FAIL_CLOSED, (), (), None, "untrusted checkpoint")
        channel = _clean_delivery()
        record = snapshot.compose(
            decision, channel.stats, channel.overflow_notices(),
            _clean_switcher())
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)

    def test_status_attention_on_real_delivery_anomaly(self):
        channel = delivery.BoundedDeliveryChannel(
            capacity=2, policy="drop_oldest", start_sequence=1)
        channel.send(1, "a")
        channel.send(2, "b")
        channel.send(3, "c")  # drops oldest -> notice + dropped counter
        record = snapshot.compose(
            _clean_startup(), channel.stats, channel.overflow_notices(),
            _clean_switcher())
        self.assertGreater(record.delivery.dropped, 0)
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_ok_on_clean_start_and_delivery(self):
        record = _compose_clean()
        self.assertEqual(record.status, snapshot.STATUS_OK)
        self.assertFalse(record.is_blocked)

    def test_contradictory_startup_flags_fail_closed(self):
        # ``READY`` derives safe_to_start=True, while a non-empty unwind
        # tuple derives needs_rollback=True. Both cannot describe one durable
        # decision: publishing STATUS_OK from these contradictory flags would
        # be a false reliability claim.
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, ("shell",), ("shell",), "shell",
            "ready but still unwinding")
        channel = _clean_delivery()
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(
                decision, channel.stats, channel.overflow_notices(),
                _clean_switcher())

    def test_overridden_startup_flags_fail_closed(self):
        # A subclass still passes isinstance(), so the snapshot must re-derive
        # the flags from the durable action/unwind tuple rather than trusting
        # overridden properties that hide a real rollback.
        class Forged(checkpoints.RecoveryDecision):
            @property
            def safe_to_start(self):
                return True

            @property
            def needs_rollback(self):
                return False

        decision = Forged(
            checkpoints.ROLLBACK, ("shell",), ("shell",), "shell",
            "partial startup; unwind durable steps")
        channel = _clean_delivery()
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(
                decision, channel.stats, channel.overflow_notices(),
                _clean_switcher())

    def test_rollback_without_unwind_steps_is_still_blocked(self):
        # recover() legitimately emits ROLLBACK with an empty unwind tuple
        # when a crash precedes the first completed step. The consistency
        # guard must not reject this legal degraded decision.
        decision = checkpoints.RecoveryDecision(
            checkpoints.ROLLBACK, (), (), None,
            "partial startup; unwind durable steps")
        channel = _clean_delivery()
        record = snapshot.compose(
            decision, channel.stats, channel.overflow_notices(),
            _clean_switcher())
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)
        self.assertTrue(record.is_blocked)
        self.assertEqual(record.startup.unwind_count, 0)

    def test_wrong_component_types_fail_closed(self):
        channel = _clean_delivery()
        good = (_clean_startup(), channel.stats, channel.overflow_notices(),
                _clean_switcher())
        # An empty tuple is the valid "no notices" value, so it is not a
        # wrong-type fixture for any component.
        bad_values = (None, 7, "token", [], {})
        for index in range(4):
            for bad in bad_values:
                args = list(good)
                args[index] = bad
                with self.subTest(index=index, bad=type(bad).__name__):
                    with self.assertRaises(snapshot.SnapshotError):
                        snapshot.compose(*args)

    def test_malformed_notice_entries_fail_closed(self):
        channel = _clean_delivery()
        for bad in ((None,), ("text",), (delivery.OverflowNotice(1, "p", 0), 7)):
            with self.subTest(bad=bad):
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.compose(
                        _clean_startup(), channel.stats, bad, _clean_switcher())

    def test_invalid_counters_and_flags_fail_closed(self):
        channel = _clean_delivery()
        base = channel.stats
        for bad in (-1, True, "3", 1.5):
            with self.subTest(bad=bad):
                bad_stats = delivery.DeliveryStats(**{
                    **base.__dict__, "sent": bad})
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.compose(
                        _clean_startup(), bad_stats, (), _clean_switcher())

    def test_long_reason_is_bounded(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, (), (), None, "x" * 5000)
        channel = _clean_delivery()
        record = snapshot.compose(
            decision, channel.stats, channel.overflow_notices(),
            _clean_switcher())
        self.assertEqual(len(record.startup.reason), snapshot.MAX_REASON_CHARS)

    def test_switcher_order_is_bounded_even_for_oversized_view(self):
        # SwitchState is a frozen public dataclass; a caller can hand the
        # snapshot an oversized view. The snapshot must cap what it records.
        oversized = switcher.SwitchState(False, None, None, tuple(range(1, 101)))
        channel = _clean_delivery()
        record = snapshot.compose(
            _clean_startup(), channel.stats, channel.overflow_notices(),
            oversized)
        self.assertEqual(record.switcher.window_count, 100)
        self.assertEqual(len(record.switcher.order), snapshot.MAX_WINDOWS)
        self.assertEqual(record.switcher.order, tuple(range(1, snapshot.MAX_WINDOWS + 1)))

    def test_no_acceptance_or_execution_claim(self):
        record = _compose_clean()
        self.assertEqual(record.acceptance, snapshot.ACCEPTANCE_NOT_ESTABLISHED)
        view = _plain(record.to_dict())
        encoded = json.dumps(view).lower()
        for forbidden in ("approved", "mint_ran", "qt_accepted"):
            self.assertNotIn(forbidden, encoded)

    def test_module_is_pure(self):
        source = (Path(snapshot.__file__).read_text(encoding="utf-8"))
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = {"time", "datetime", "random", "subprocess", "socket",
                     "threading", "asyncio", "os", "tempfile"}
        self.assertFalse(imported & forbidden)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
