"""Tests for the bounded, immutable host-facing session-lifecycle snapshot.

The snapshot composes three already-tested state models (lock/session events,
theme rollback and focus intents) into one deterministic host-facing record.
These tests pin the contract: pure composition, bounded embedded collections,
immutable views, deterministic bytes, explicit status derivation and
fail-closed input validation.
"""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.reliability import lock_session_events as lock
from canopy_features.reliability import session_lifecycle_snapshot as snapshot
from canopy_features.reliability import theme_transition_rollback as theme
from canopy_features.windows import focus_intents as focus


def _plain(value):
    """Recursively turn MappingProxyType views into plain dicts for JSON."""
    if isinstance(value, MappingProxyType):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _clean_parts():
    session = lock.Reconciler(initial_locked=False)
    ledger = theme.ThemeTransitionRollback()
    policy = focus.PermissionPolicy()
    broker = focus.FocusBroker(policy.authorize)
    return session, ledger, broker, policy


def _compose_clean():
    return snapshot.compose(*_clean_parts())


def _encode(record):
    return json.dumps(_plain(record.to_dict()), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class SessionLifecycleSnapshotTests(unittest.TestCase):
    def test_composes_real_state_models(self):
        record = _compose_clean()
        self.assertIsInstance(record, snapshot.SessionLifecycleSnapshot)
        self.assertEqual(record.schema, snapshot.SCHEMA)
        self.assertEqual(record.status, snapshot.STATUS_OK)
        self.assertIsInstance(record.session, snapshot.SessionView)
        self.assertIsInstance(record.theme, snapshot.ThemeView)
        self.assertIsInstance(record.focus, snapshot.FocusView)
        self.assertEqual(record.session.label, "active")
        self.assertEqual(record.session.accepted, 0)
        self.assertEqual(record.theme.state, theme.IDLE)
        self.assertIsNone(record.theme.active)
        self.assertEqual(record.focus.live_windows, 0)
        self.assertEqual(record.focus.grant_count, 0)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        for target, field in ((record, "status"), (record.session, "label"),
                              (record.theme, "state"), (record.focus, "grant_count")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_is_a_fresh_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertIsInstance(view["session"], MappingProxyType)
        self.assertIsInstance(view["theme"], MappingProxyType)
        self.assertIsInstance(view["focus"], MappingProxyType)
        with self.assertRaises(TypeError):
            view["status"] = "mutated"
        with self.assertRaises(TypeError):
            view["theme"]["state"] = "mutated"
        again = record.to_dict()
        self.assertIsNot(again, view)
        self.assertEqual(again, view)

    def test_to_dict_key_order_is_fixed(self):
        record = _compose_clean()
        view = record.to_dict()
        self.assertEqual(tuple(view), (
            "schema", "status", "acceptance", "event_observation",
            "session", "theme", "focus"))
        self.assertEqual(tuple(view["session"]), (
            "label", "suspended", "locked", "accepted", "recent_statuses"))
        self.assertEqual(tuple(view["theme"]), (
            "state", "active", "candidate", "single_owner",
            "live_resource_count", "abandoned"))
        self.assertEqual(tuple(view["focus"]), (
            "live_windows", "grant_count", "recent_statuses"))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))

    def test_is_blocked_matches_status(self):
        self.assertFalse(_compose_clean().is_blocked)
        session = lock.Reconciler()
        blocked = snapshot.compose(session, theme.ThemeTransitionRollback(),
                                   focus.FocusBroker(lambda *_: False))
        self.assertTrue(blocked.is_blocked)
        self.assertEqual(blocked.status, snapshot.STATUS_BLOCKED)

    def test_session_history_is_bounded(self):
        session = lock.Reconciler(initial_locked=False, history_limit=32)
        for tick in range(20):
            outcome = session.observe(lock.SessionEvent(
                lock.LOCK if tick % 2 == 0 else lock.UNLOCK, float(tick + 1)))
            self.assertTrue(outcome.transitioned)
        record = snapshot.compose(session, theme.ThemeTransitionRollback(),
                                  focus.FocusBroker(lambda *_: True))
        self.assertEqual(len(session.history), 20)
        self.assertEqual(record.session.recent_statuses,
                         (lock.TRANSITION,) * snapshot.MAX_RECENT)

    def test_focus_history_is_bounded(self):
        session, ledger, broker, _policy = _clean_parts()
        ref = broker.register_window("same.app", 10)
        for _ in range(20):
            broker.request_focus(focus.FocusIntent("same.app", ref))
        record = snapshot.compose(session, ledger, broker, _policy)
        self.assertEqual(len(broker.history), 20)
        self.assertEqual(record.focus.recent_statuses,
                         (focus.GRANTED,) * snapshot.MAX_RECENT)

    def test_abandoned_resources_are_bounded_and_sorted(self):
        ledger = theme.ThemeTransitionRollback("base", {"r0"})
        for index in range(1, 17):
            self.assertEqual(ledger.prepare("t%d" % index,
                                            {"r%d" % index}), "PREPARED")
            self.assertEqual(ledger.commit(), "COMMITTED")
        record = snapshot.compose(lock.Reconciler(initial_locked=False),
                                  ledger, focus.FocusBroker(lambda *_: True))
        self.assertEqual(len(record.theme.abandoned), theme.ThemeTransitionRollback.MAX_ABANDONED)
        self.assertLessEqual(len(record.theme.abandoned), snapshot.MAX_THEME_NAMES)
        self.assertEqual(record.theme.abandoned,
                         tuple(sorted("r%d" % i for i in range(16))))

    def test_status_blocked_on_locked_or_suspended_session(self):
        session = lock.Reconciler()
        record = snapshot.compose(session, theme.ThemeTransitionRollback(),
                                  focus.FocusBroker(lambda *_: True))
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)
        active = lock.Reconciler(initial_locked=False)
        active.observe(lock.SessionEvent(lock.SUSPEND, 1.0))
        suspended = snapshot.compose(active, theme.ThemeTransitionRollback(),
                                     focus.FocusBroker(lambda *_: True))
        self.assertEqual(suspended.status, snapshot.STATUS_BLOCKED)
        self.assertEqual(suspended.session.label, "suspended")

    def test_status_blocked_on_uncommitted_theme_switch(self):
        ledger = theme.ThemeTransitionRollback("base", {"r0"})
        self.assertEqual(ledger.prepare("candidate", {"r1"}), "PREPARED")
        record = snapshot.compose(lock.Reconciler(initial_locked=False), ledger,
                                  focus.FocusBroker(lambda *_: True))
        self.assertEqual(record.theme.state, theme.PREPARED)
        self.assertEqual(record.theme.candidate, "candidate")
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)

    def test_status_blocked_on_failed_focus_decision(self):
        session, ledger, broker, policy = _clean_parts()
        ref = broker.register_window("owner.app", 10)
        decision = broker.request_focus(focus.FocusIntent("other.app", ref))
        self.assertEqual(decision.status, focus.DENIED)
        record = snapshot.compose(session, ledger, broker, policy)
        self.assertEqual(record.focus.recent_statuses, (focus.DENIED,))
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)

    def test_status_attention_on_abandoned_resources(self):
        ledger = theme.ThemeTransitionRollback("base", {"r0"})
        ledger.prepare("next", {"r1"})
        ledger.commit()
        record = snapshot.compose(lock.Reconciler(initial_locked=False),
                                  ledger, focus.FocusBroker(lambda *_: True))
        self.assertTrue(record.theme.single_owner)
        self.assertEqual(record.theme.abandoned, ("r0",))
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_attention_on_session_churn(self):
        session = lock.Reconciler(initial_locked=False)
        session.observe(lock.SessionEvent(lock.LOCK, 1.0))
        session.observe(lock.SessionEvent(lock.UNLOCK, 2.0))
        record = snapshot.compose(session, theme.ThemeTransitionRollback(),
                                  focus.FocusBroker(lambda *_: True))
        self.assertEqual(record.session.label, "active")
        self.assertEqual(record.session.accepted, 2)
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_attention_on_cross_app_grant(self):
        session, ledger, broker, policy = _clean_parts()
        policy.grant("origin.app", "target.app")
        record = snapshot.compose(session, ledger, broker, policy)
        self.assertEqual(record.focus.grant_count, 1)
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_granted_focus_alone_stays_ok(self):
        session, ledger, broker, policy = _clean_parts()
        ref = broker.register_window("same.app", 10)
        self.assertTrue(broker.request_focus(
            focus.FocusIntent("same.app", ref)).allowed)
        record = snapshot.compose(session, ledger, broker, policy)
        self.assertEqual(record.focus.live_windows, 1)
        self.assertEqual(record.focus.recent_statuses, (focus.GRANTED,))
        self.assertEqual(record.status, snapshot.STATUS_OK)

    def test_policy_is_optional(self):
        session, ledger, broker, _policy = _clean_parts()
        record = snapshot.compose(session, ledger, broker)
        self.assertIsNone(record.focus.grant_count)
        self.assertEqual(record.status, snapshot.STATUS_OK)

    def test_wrong_component_types_fail_closed(self):
        session, ledger, broker, policy = _clean_parts()
        for position, bad_values in (
                ("session", (None, object(), ledger, broker, policy, "x")),
                ("theme", (None, object(), session, broker, policy, 7)),
                ("focus", (None, object(), session, ledger, policy, "x")),
                ("policy", (object(), 7, "x", [], session))):
            for bad in bad_values:
                with self.subTest(position=position, bad=type(bad).__name__):
                    args = [session, ledger, broker, policy]
                    args[("session", "theme", "focus", "policy").index(position)] = bad
                    with self.assertRaises(snapshot.SnapshotError):
                        snapshot.compose(*args)

    def test_contradictory_session_label_is_rejected(self):
        class BadState(lock.SessionState):
            @property
            def label(self):
                return "locked"

        class BadReconciler(lock.Reconciler):
            @property
            def state(self):
                return BadState(False, False)

        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(BadReconciler(initial_locked=False),
                             theme.ThemeTransitionRollback(),
                             focus.FocusBroker(lambda *_: True))

    def test_contradictory_owner_flag_is_rejected(self):
        class BadSnapshot(theme.Snapshot):
            @property
            def single_owner(self):
                return True

        class BadLedger(theme.ThemeTransitionRollback):
            def snapshot(self):
                return BadSnapshot(
                    state=theme.IDLE, active=None, candidate=None,
                    live_resources=frozenset({"a"}),
                    abandoned_resources=frozenset({"a"}))

        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(lock.Reconciler(initial_locked=False),
                             BadLedger(), focus.FocusBroker(lambda *_: True))

    def test_oversized_theme_names_are_bounded(self):
        class LongLedger(theme.ThemeTransitionRollback):
            def snapshot(self):
                return theme.Snapshot(
                    state=theme.IDLE, active="A" * 400,
                    candidate="B" * 400, live_resources=frozenset(),
                    abandoned_resources=frozenset())

        record = snapshot.compose(lock.Reconciler(initial_locked=False),
                                  LongLedger(),
                                  focus.FocusBroker(lambda *_: True))
        self.assertEqual(len(record.theme.active), snapshot.MAX_CHARS)
        self.assertEqual(len(record.theme.candidate), snapshot.MAX_CHARS)

    def test_no_acceptance_or_observation_claim(self):
        session = lock.Reconciler()
        session.observe(lock.SessionEvent(lock.SUSPEND, 1.0))
        ledger = theme.ThemeTransitionRollback("base", {"r0"})
        ledger.prepare("next", {"r1"})
        broker = focus.FocusBroker(lambda *_: True)
        ref = broker.register_window("a.app", 1)
        broker.request_focus(focus.FocusIntent("b.app", ref))
        record = snapshot.compose(session, ledger, broker)
        encoded = _encode(record)
        self.assertEqual(record.acceptance, snapshot.ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.event_observation,
                         snapshot.EVENT_OBSERVATION_NOT_PERFORMED)
        self.assertIn(b'"acceptance":"NOT_ESTABLISHED"', encoded)
        self.assertIn(b'"event_observation":"NOT_PERFORMED"', encoded)
        for forbidden in (b"APPROVED", b"MINT_RAN", b"QT_ACCEPTED",
                          b"OBSERVED", b"PROVEN"):
            self.assertNotIn(forbidden, encoded)

    def test_module_is_pure(self):
        source = (Path(__file__).resolve().parents[1] / "canopy_features"
                  / "reliability" / "session_lifecycle_snapshot.py").read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"time", "datetime", "random", "subprocess", "socket",
                     "threading", "os", "sys", "pathlib", "shutil", "tempfile"}
        self.assertFalse(imported & forbidden)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
