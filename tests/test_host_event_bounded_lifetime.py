"""Regression for host-event liveness, fairness and bounded catalog refresh.

The production fix lives in ``prototype/classic/main.cpp``: a lazy token bucket
(capacity 16, one refill per second), a fixed 16-entry outcome history and a
four-entry catalog-refresh fingerprint ring replace the old 64-dispatch
lifetime freeze. This follow-up adds one boolean pending-refresh latch: a fresh
``app.catalog.changed`` refresh is emitted before its token is charged, or
latched when the bucket is empty and flushed by the next real dispatch that
observes a token. Authoritative state commits are never reported as failed.

This module locks those source contracts and drives an executable model of the
exact algorithm with an injected clock, so a 17-valid-events-per-tick flood
cannot starve catalog refresh without sleeping or polling. It is a SYNTHETIC
model proof: no Qt instance, compiled self-test, Mint guest, screen reader,
transport or visual acceptance is claimed here.
"""
from __future__ import annotations

import re
import unittest
from collections import deque
from pathlib import Path

from canopy_core.host_events import (
    HostEventError,
    HostEvents,
    TOPICS,
    _encode_fields,
)

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "prototype" / "classic" / "main.cpp"
WINDOW_KEYS = ("schema", "backend", "negotiation", "sequence", "installed",
               "owners", "grants", "launcherEnabled")
BACKENDS = frozenset({"x11", "wayland", "headless"})
NEGOTIATIONS = frozenset({"SUPPORTED", "PARTIAL", "UNSUPPORTED"})
SOURCE_RE = re.compile(r"[a-z0-9_.:-]{0,64}\Z")
CREDENTIAL_FIELDS = ("password", "user_password", "access_token", "api_key",
                     "secret", "token", "__proto__")


def bridge_block() -> str:
    source = MAIN.read_text(encoding="utf-8")
    start = source.index("class ClassicHostEventBridge final : public QObject")
    return source[start:source.index("\n};", start)]


def main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


def constant(name: str) -> int:
    match = re.search(
        r"static constexpr (?:int|qint64) %s = (\d+);" % name, bridge_block())
    assert match is not None, "missing fixed-size constant " + name
    return int(match.group(1))


class Clock:
    """Injected monotonic clock: no sleep, timer thread or real time."""

    def __init__(self):
        self.ms = 0

    def __call__(self):
        return self.ms


class BoundedLifetimeBridge:
    """Executable model of the compiled ClassicHostEventBridge algorithm."""

    def __init__(self, clock, capacity, refill_ms, history_max, dedup_max):
        self.clock = clock
        self.capacity = capacity
        self.refill_ms = refill_ms
        self.history_max = history_max
        self.dedup_max = dedup_max
        self.tokens = capacity
        self.last = clock()
        self.history = deque(maxlen=history_max)
        self.dedup = deque(maxlen=dedup_max)
        self.total = self.accepted = self.rejected = 0
        self.refresh_signals = 0
        self.refresh_pending = False
        self.last_outcome = "unset"

    def _record(self, outcome):
        if outcome in ("rejected", "window-rejected"):
            self.rejected += 1
        else:
            self.accepted += 1
        self.last_outcome = outcome
        self.history.append(outcome)

    def _refill(self):
        current = self.clock()
        if current <= self.last:
            return
        elapsed = current - self.last
        steps = elapsed // self.refill_ms
        if steps <= 0:
            return
        self.tokens = min(self.capacity,
                          self.tokens + min(steps, self.capacity))
        self.last = current - (elapsed % self.refill_ms)

    def _take(self):
        self._refill()
        if self.tokens == 0:
            return False
        self.tokens -= 1
        return True

    def _flush_pending(self):
        if self.refresh_pending and self.tokens > 0:
            self.refresh_pending = False
            self.refresh_signals += 1

    @staticmethod
    def _quick_ok(payload):
        for key, value in payload.items():
            if key in ("network_connected", "audio_muted", "battery_charging",
                       "settings_bridge") and type(value) is not bool:
                return False
            if key in ("volume_percent", "brightness_percent"):
                if type(value) is not int or not 0 <= value <= 100:
                    return False
            if key == "source" and (
                    type(value) is not str or not SOURCE_RE.fullmatch(value)):
                return False
        return True

    @staticmethod
    def _window_ok(payload):
        if any(key not in payload for key in WINDOW_KEYS):
            return False
        return (type(payload.get("schema")) is int and payload["schema"] == 1
                and type(payload.get("sequence")) is int
                and payload["sequence"] >= 0
                and type(payload.get("backend")) is str
                and payload["backend"] in BACKENDS
                and type(payload.get("negotiation")) is str
                and payload["negotiation"] in NEGOTIATIONS
                and type(payload.get("launcherEnabled")) is bool)

    def dispatch(self, topic, payload):
        self.total += 1
        self._refill()
        self._flush_pending()
        if type(topic) is not str or topic not in TOPICS or not payload:
            self._record("rejected")
            return False
        if topic in ("capabilities.report", "session.state.changed"):
            if not self._quick_ok(payload):
                self._record("rejected")
                return False
            throttled = not self._take()
            if topic == "capabilities.report":
                self._record("quick-controls-applied-deferred" if throttled
                             else "quick-controls-applied")
            else:
                self._record("session-observed-deferred" if throttled
                             else "session-observed")
            return True
        if topic == "window.state.changed":
            if not self._window_ok(payload):
                self._record("window-rejected")
                return False
            throttled = not self._take()
            self._record("window-applied-deferred" if throttled
                         else "window-applied")
            return True
        fingerprint = (self.last // self.refill_ms,
                       tuple(sorted((str(k), str(v), type(v).__name__)
                                    for k, v in payload.items())))
        if fingerprint in self.dedup:
            self._record("catalog-refresh-coalesced")
            return True
        self.dedup.append(fingerprint)
        if self.tokens > 0:
            self.refresh_signals += 1
            self._take()
            self._record("catalog-refresh-requested")
        else:
            self.refresh_pending = True
            self._record("catalog-refresh-pending")
        return True


def new_bridge(clock):
    return BoundedLifetimeBridge(
        clock, constant("kBucketCapacity"), constant("kRefillMs"),
        constant("kMaxHistory"), constant("kDuplicateWindow"))


def window_payload():
    return {"schema": 1, "backend": "x11", "negotiation": "SUPPORTED",
            "sequence": 1, "installed": True, "owners": [], "grants": [],
            "launcherEnabled": True}


class BoundedHostEventLifetimeTests(unittest.TestCase):
    def test_source_has_no_lifetime_freeze_or_wakeup(self):
        block = bridge_block()
        for removed in ("kMaxEvents", "frozen()", "refresh-limit", "QTimer("):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, block)
        for marker in ("kBucketCapacity", "kRefillMs", "kDuplicateWindow",
                       "takeToken()", "refill()", "refreshFingerprint(",
                       "m_lastRefillMs = current - (elapsed % kRefillMs);",
                       "m_refreshPending", "flushPendingRefresh()",
                       "catalog-refresh-pending",
                       "quick-controls-applied-deferred"):
            with self.subTest(marker=marker):
                self.assertIn(marker, block)
        for forbidden in ("QThread", "QProcess", "QTcpSocket", "QUdpSocket",
                          "sleep(", "while (", "for (;;)", "QQueue",
                          "std::deque", "std::vector"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)
        self.assertEqual((constant("kBucketCapacity"), constant("kRefillMs"),
                          constant("kMaxHistory"), constant("kDuplicateWindow")),
                         (16, 1000, 16, 4))

    def test_200_spaced_valid_dispatches_continue_past_64(self):
        clock = Clock()
        bridge = new_bridge(clock)
        outcomes = []
        for index in range(200):
            clock.ms += constant("kRefillMs")
            payload = (window_payload() if index % 4 == 0 else
                       {"network_connected": True, "volume_percent": 33})
            topic = ("window.state.changed" if index % 4 == 0 else
                     "capabilities.report")
            payload["sequence"] = index
            outcomes.append(bridge.dispatch(topic, payload))
        self.assertTrue(all(outcomes), "a valid dispatch was rejected past 64")
        self.assertEqual(bridge.total, 200)
        self.assertEqual(bridge.accepted, 200)
        self.assertEqual(bridge.rejected, 0)
        self.assertEqual(len(bridge.history), constant("kMaxHistory"))
        self.assertLessEqual(len(bridge.dedup), constant("kDuplicateWindow"))
        self.assertEqual(sum(outcomes[64:]), 136)

    def test_same_tick_burst_is_bounded_and_outcomes_are_truthful(self):
        clock = Clock()
        bridge = new_bridge(clock)
        outcomes = []
        for _ in range(200):
            ok = bridge.dispatch("capabilities.report",
                                 {"network_connected": True})
            outcomes.append((ok, bridge.last_outcome))
        self.assertEqual(sum(ok for ok, _ in outcomes), 200)
        self.assertTrue(all(ok for ok, _ in outcomes),
                        "a committed state event must not return false")
        self.assertEqual(sum(1 for _, outcome in outcomes
                             if outcome == "quick-controls-applied"),
                         constant("kBucketCapacity"))
        self.assertEqual(sum(1 for _, outcome in outcomes
                             if outcome == "quick-controls-applied-deferred"),
                         200 - constant("kBucketCapacity"))
        self.assertEqual(bridge.rejected, 0)
        self.assertEqual(len(bridge.history), constant("kMaxHistory"))
        self.assertEqual(list(bridge.history),
                         ["quick-controls-applied-deferred"] * 16)
        self.assertEqual(bridge.tokens, 0)
        self.assertFalse(bridge.refresh_pending)

    def test_committed_window_and_session_state_never_return_false(self):
        clock = Clock()
        bridge = new_bridge(clock)
        for _ in range(constant("kBucketCapacity")):
            bridge.dispatch("capabilities.report", {"network_connected": True})
        self.assertTrue(bridge.dispatch("window.state.changed", window_payload()))
        self.assertEqual(bridge.last_outcome, "window-applied-deferred")
        self.assertTrue(bridge.dispatch("session.state.changed",
                                        {"settings_bridge": True}))
        self.assertEqual(bridge.last_outcome, "session-observed-deferred")
        self.assertEqual(bridge.rejected, 0)

    def test_catalog_duplicate_suppression_and_history_stay_bounded(self):
        clock = Clock()
        bridge = new_bridge(clock)
        token = {"source": "host-events"}
        for _ in range(10):
            self.assertTrue(bridge.dispatch("app.catalog.changed", token))
        self.assertEqual(bridge.refresh_signals, 1)
        self.assertEqual(bridge.last_outcome, "catalog-refresh-coalesced")
        self.assertEqual(len(bridge.dedup), 1)
        for tick in range(1, 101):
            clock.ms += constant("kRefillMs")
            bridge.dispatch("app.catalog.changed", token)
            self.assertLessEqual(len(bridge.history), constant("kMaxHistory"))
            self.assertLessEqual(len(bridge.dedup),
                                 constant("kDuplicateWindow"))
        self.assertEqual(bridge.refresh_signals, 101)
        self.assertEqual(len(bridge.dedup), constant("kDuplicateWindow"))
        self.assertEqual(len(bridge.history), constant("kMaxHistory"))

    def test_catalog_refresh_survives_17_valid_events_per_tick_flood(self):
        """The exact starvation scenario from the PR724 liveness audit."""
        clock = Clock()
        bridge = new_bridge(clock)
        for tick in range(1, 21):
            clock.ms += constant("kRefillMs")
            for index in range(17):
                if index < 16:
                    topic = "capabilities.report"
                    payload = {"network_connected": True,
                               "volume_percent": index}
                else:
                    topic = "app.catalog.changed"
                    payload = {"count": tick}
                self.assertTrue(bridge.dispatch(topic, payload),
                                "valid flood event was reported as failed")
            self.assertTrue(bridge.refresh_pending,
                            "fresh catalog refresh was not latched at tick %d"
                            % tick)
            self.assertEqual(bridge.tokens, 0)
            self.assertLessEqual(len(bridge.dedup), constant("kDuplicateWindow"))
            self.assertLessEqual(len(bridge.history), constant("kMaxHistory"))
        self.assertEqual(bridge.refresh_signals, 19)
        clock.ms += constant("kRefillMs")
        self.assertTrue(bridge.dispatch("capabilities.report",
                                        {"network_connected": True}))
        self.assertEqual(bridge.refresh_signals, 20)
        self.assertFalse(bridge.refresh_pending)
        self.assertEqual(bridge.total, 20 * 17 + 1)
        self.assertEqual(bridge.rejected, 0)

    def test_no_polling_timer_thread_new_topic_or_unbounded_queue(self):
        block = bridge_block()
        for forbidden in ("QTimer", "QThread", "QProcess", "QTcpSocket",
                          "QUdpSocket", "sleep(", "msleep", "while (",
                          "for (;;)", "poll(", "QQueue", "std::deque",
                          "std::list", "std::vector", "registerTopic",
                          "dynamicTopic"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, block)
        topics = re.findall(r'QStringLiteral\("([a-z.]+\.[a-z.]+)"\)', block)
        self.assertEqual(set(topics), set(TOPICS), "no fifth topic may be added")
        self.assertIn('bool m_refreshPending = false;', block)
        self.assertNotIn("QVariantMap m_pending", block)
        self.assertEqual(main_source().count("launcherCatalog.loadFromFile("), 1)

    def test_negative_controls_allowlist_payload_and_credentials(self):
        clock = Clock()
        bridge = new_bridge(clock)
        bad = (
            ("wifi.scan.changed", {"source": "host-events"}),
            ("capabilities.report", {}),
            ("window.state.changed", {"focus_app": "Files"}),
            ("capabilities.report", {"volume_percent": 999}),
            ("session.state.changed", {"settings_bridge": "yes"}),
        )
        for topic, payload in bad:
            with self.subTest(topic=topic, payload=payload):
                self.assertFalse(bridge.dispatch(topic, payload))
        self.assertEqual(bridge.accepted, 0)
        self.assertEqual(bridge.refresh_signals, 0)
        self.assertEqual(bridge.tokens, constant("kBucketCapacity"))
        self.assertFalse(bridge.refresh_pending)

        seen = []
        callback = seen.append
        bus = HostEvents({"app.catalog.changed": [callback]})
        bus.subscribe("app.catalog.changed", callback)
        for field in CREDENTIAL_FIELDS:
            with self.subTest(field=field):
                with self.assertRaises(HostEventError) as caught:
                    bus.emit("app.catalog.changed", {field: "SENSITIVE"})
                self.assertEqual(str(caught.exception),
                                 "unsupported host event field name")
                with self.assertRaises(HostEventError):
                    _encode_fields({field: "SENSITIVE"})
        self.assertEqual(seen, [])
        self.assertEqual(bus.emit("app.catalog.changed", {"count": 1}).delivered, 1)

        literals = set(re.findall(r'QStringLiteral\("([^"]+)"\)', bridge_block()))
        self.assertFalse(literals & set(CREDENTIAL_FIELDS),
                         "no credential field may enter the compiled dispatcher")


if __name__ == "__main__":
    unittest.main()
