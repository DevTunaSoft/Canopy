"""PE-110: bounded panel/session lifecycle notification contracts.

Offline, synthetic-only tests. No real session, compositor, VM, D-Bus, daemon,
credential, Qt runtime, filesystem or network access is used. Every event is an
in-memory protocol-v2 ``HostEvent`` delivered by the trusted in-process bus.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from canopy_core.host_events import PROTOCOL_VERSION, TOPICS, HostEvent

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "canopy_features" / "notifications" / "panel_lifecycle.py"


def contract():
    """Import lazily so an absent module is a fast, explicit RED."""
    from canopy_features.notifications import panel_lifecycle
    return panel_lifecycle


def active(lifecycle):
    return lifecycle.publish(contract().SESSION_TOPIC, {"state": "active"})


class ContractBoundaryTests(unittest.TestCase):
    def test_no_new_topic_or_protocol_version(self):
        m = contract()
        self.assertEqual(m.PROTOCOL_VERSION, PROTOCOL_VERSION)
        self.assertEqual(TOPICS, frozenset({
            "app.catalog.changed", "window.state.changed",
            "session.state.changed", "capabilities.report",
        }))
        self.assertEqual(m.SESSION_TOPIC, "session.state.changed")
        self.assertIn(m.SESSION_TOPIC, TOPICS)
        self.assertEqual(m.SESSION_STATUS,
                         frozenset({"active", "locked", "suspended", "unknown"}))
        self.assertEqual(m.SOURCE, "host-events")

    def test_no_transport_or_execution_imports(self):
        m = contract()
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"os", "sys", "subprocess", "socket", "shutil", "signal",
                     "threading", "asyncio", "dbus", "time"}
        self.assertFalse(imported & forbidden)
        source = MODULE_PATH.read_text(encoding="utf-8")
        for token in ("panel.state.changed", "systemctl", "loginctl",
                      "os.system", "Popen", "exec("):
            self.assertNotIn(token, source)


class FailClosedTests(unittest.TestCase):
    def test_default_view_is_closed_unobserved_and_empty(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        view = path.snapshot()
        self.assertEqual(view["panel"], m.PANEL_CLOSED)
        self.assertEqual(view["session"], m.STATUS_UNKNOWN)
        self.assertEqual(view["reason"], m.REASON_NO_OBSERVATION)
        self.assertFalse(view["surfacing"])
        self.assertEqual(view["records"], ())
        self.assertEqual(view["status"], m.UNAVAILABLE)
        self.assertEqual(view["disclosure"], m.DISCLOSURES[view["reason"]])
        path.close()

    def test_panel_open_without_active_session_stays_empty(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        self.assertTrue(path.open_panel())
        path.publish("app.catalog.changed", {"item_count": 3, "available": True})
        view = path.snapshot()
        self.assertEqual(view["panel"], m.PANEL_OPEN)
        self.assertEqual(view["session"], m.STATUS_UNKNOWN)
        self.assertEqual(view["reason"], m.REASON_NO_OBSERVATION)
        self.assertEqual(view["records"], ())
        path.close()

    def test_active_session_with_closed_panel_stays_empty_then_surfaces(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        self.assertEqual(path.snapshot()["records"], ())
        self.assertTrue(path.open_panel())
        view = path.snapshot()
        self.assertEqual(view["reason"], m.REASON_OK)
        self.assertTrue(view["surfacing"])
        self.assertEqual(len(view["records"]), 1)
        self.assertEqual(view["records"][0]["topic"], m.SESSION_TOPIC)
        self.assertEqual(view["records"][0]["source"], m.SOURCE)
        path.close()

    def test_locked_session_obscures_panel_and_clears_surface(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        path.open_panel()
        self.assertEqual(len(path.snapshot()["records"]), 1)
        path.publish(m.SESSION_TOPIC, {"state": "locked"})
        view = path.snapshot()
        self.assertEqual(view["panel"], m.PANEL_OBSCURED)
        self.assertEqual(view["session"], "locked")
        self.assertEqual(view["reason"], m.REASON_PANEL_OBSCURED)
        self.assertEqual(view["records"], ())
        with self.assertRaises(m.PanelLifecycleError):
            path.open_panel()
        path.close()

    def test_return_to_active_requires_explicit_acknowledgement(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        path.open_panel()
        path.publish(m.SESSION_TOPIC, {"state": "suspended"})
        self.assertEqual(path.snapshot()["panel"], m.PANEL_OBSCURED)
        path.publish(m.SESSION_TOPIC, {"state": "active"})
        self.assertTrue(path.snapshot()["needs_reobservation"])
        self.assertEqual(path.snapshot()["reason"], m.REASON_PANEL_OBSCURED)
        self.assertEqual(path.snapshot()["records"], ())
        with self.assertRaises(m.PanelLifecycleError):
            path.open_panel()
        path.acknowledge_reobservation()
        self.assertTrue(path.open_panel())
        self.assertEqual(path.snapshot()["reason"], m.REASON_OK)
        self.assertTrue(path.snapshot()["records"])
        path.close()

    def test_invalid_session_observation_loses_boundary_and_hides_rows(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        path.open_panel()
        with self.assertRaises(m.PanelLifecycleError) as caught:
            path.publish(m.SESSION_TOPIC, {"state": "SECRET_MARKER"})
        self.assertNotIn("SECRET_MARKER", str(caught.exception))
        view = path.snapshot()
        self.assertEqual(view["reason"], m.REASON_BOUNDARY_LOST)
        self.assertEqual(view["records"], ())
        self.assertNotIn("SECRET_MARKER", view["disclosure"])
        with self.assertRaises(m.PanelLifecycleError):
            path.publish("app.catalog.changed", {"item_count": 1})
        self.assertTrue(path.restore_host())
        self.assertEqual(path.snapshot()["reason"], m.REASON_NEEDS_REOBSERVATION)
        path.acknowledge_reobservation()
        active(path)
        self.assertEqual(path.snapshot()["reason"], m.REASON_OK)
        path.close()

    def test_host_unavailable_signal_degrades_to_unavailable(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        path.open_panel()
        path.mark_host_unavailable()
        view = path.snapshot()
        self.assertEqual(view["reason"], m.REASON_BOUNDARY_LOST)
        self.assertEqual(view["records"], ())
        self.assertFalse(view["surfacing"])
        path.close()

    def test_stale_and_duplicate_session_events_cannot_resurrect_view(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        path.open_panel()
        stale = HostEvent(PROTOCOL_VERSION, m.SESSION_TOPIC, 0,
                          (("state", "locked"),))
        path.observe(stale)
        self.assertEqual(path.snapshot()["session"], "active")
        path.observe(HostEvent(PROTOCOL_VERSION, m.SESSION_TOPIC, 1,
                               (("state", "suspended"),)))
        self.assertEqual(path.snapshot()["session"], "active")
        self.assertEqual(path.snapshot()["counts"]["stale"], 2)
        path.close()

    def test_forged_event_and_wrong_payload_types_fail_closed(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)

        class Forged(HostEvent):
            pass

        with self.assertRaises(m.PanelLifecycleError):
            path.observe(Forged(PROTOCOL_VERSION, m.SESSION_TOPIC, 2,
                                (("state", "locked"),)))
        self.assertEqual(path.snapshot()["reason"], m.REASON_BOUNDARY_LOST)
        self.assertEqual(path.snapshot()["records"], ())
        for bad in (None, [], "active", 3, {"state": ["locked"]},
                    {"other": "active"}):
            with self.assertRaises(m.PanelLifecycleError):
                path.publish(m.SESSION_TOPIC, bad)
        self.assertEqual(path.snapshot()["reason"], m.REASON_BOUNDARY_LOST)
        path.close()


class BoundsAndTypesTests(unittest.TestCase):
    def test_constructor_rejects_hostile_bounds_and_sources(self):
        m = contract()
        from canopy_features.notifications.host_event_source import (
            TrustedHostEventSource,
        )
        source = TrustedHostEventSource()
        for bad in (0, 13, True, 1.0, "3", None, [], {}):
            with self.assertRaises(m.PanelLifecycleError):
                m.PanelSessionLifecycle(max_items=bad)
            with self.assertRaises(m.PanelLifecycleError):
                m.PanelSessionLifecycle(max_history=bad)
        for bad in (source.__class__, "source", 7, [], {}, None):
            if bad is None:
                continue
            with self.assertRaises(m.PanelLifecycleError):
                m.PanelSessionLifecycle(source=bad)
        source.close()

    def test_bounded_batch_consumes_at_most_max_batch(self):
        m = contract()
        path = m.PanelSessionLifecycle(max_batch=3)
        items = [(m.SESSION_TOPIC, {"state": "active"})] + [
            ("app.catalog.changed", {"item_count": n}) for n in range(50)
        ]
        result = path.publish_many(items)
        self.assertEqual(result.consumed, 3)
        self.assertEqual(result.accepted, 3)
        self.assertIs(result.stopped, False)
        for bad in ("topic", b"topic", {"topic": "x"}, 7):
            with self.assertRaises(m.PanelLifecycleError):
                path.publish_many(bad)
        path.close()

    def test_notice_capacity_is_bounded_and_newest_first(self):
        m = contract()
        path = m.PanelSessionLifecycle(max_items=3)
        active(path)
        path.open_panel()
        for n in range(5):
            path.publish("app.catalog.changed", {"item_count": n})
        records = path.snapshot()["records"]
        self.assertEqual(len(records), 3)
        self.assertEqual([r["topic"] for r in records],
                         ["app.catalog.changed"] * 3)
        ids = [r["id"] for r in records]
        self.assertEqual(ids, sorted(set(ids), key=ids.index))
        self.assertEqual(path.snapshot()["counts"]["dropped"], 3)
        path.close()

    def test_injected_source_is_not_closed_by_lifecycle(self):
        m = contract()
        from canopy_features.notifications.host_event_source import (
            TrustedHostEventSource,
        )
        source = TrustedHostEventSource()
        path = m.PanelSessionLifecycle(source=source)
        path.close()
        self.assertTrue(source.connected())
        source.close()

    def test_source_loss_produces_no_rows(self):
        m = contract()
        from canopy_features.notifications.host_event_source import (
            TrustedHostEventSource,
        )
        source = TrustedHostEventSource()
        path = m.PanelSessionLifecycle(source=source)
        active(path)
        path.open_panel()
        self.assertTrue(path.snapshot()["records"])
        source.close()
        view = path.snapshot()
        self.assertEqual(view["reason"], m.REASON_SOURCE_LOST)
        self.assertEqual(view["records"], ())
        path.close()

    def test_close_is_idempotent_and_fail_closed(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        path.open_panel()
        path.close()
        path.close()
        view = path.snapshot()
        self.assertEqual(view["reason"], m.REASON_CLOSED)
        self.assertEqual(view["panel"], m.PANEL_CLOSED)
        self.assertEqual(view["records"], ())
        with self.assertRaises(m.PanelLifecycleError):
            path.publish(m.SESSION_TOPIC, {"state": "active"})
        with self.assertRaises(m.PanelLifecycleError):
            path.open_panel()

    def test_snapshot_is_immutable_and_to_dict_is_deterministic(self):
        m = contract()
        path = m.PanelSessionLifecycle()
        active(path)
        path.open_panel()
        view = path.snapshot()
        with self.assertRaises(TypeError):
            view["panel"] = m.PANEL_CLOSED
        with self.assertRaises(TypeError):
            view["records"][0]["id"] = "forged"
        first = path.to_dict()
        second = path.to_dict()
        self.assertEqual(first, second)
        self.assertEqual(first["source"], m.SOURCE)
        self.assertEqual(set(first["records"][0]),
                         {"id", "title", "body", "source", "topic"})
        path.close()


if __name__ == "__main__":
    unittest.main()
