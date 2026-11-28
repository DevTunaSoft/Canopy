"""Native Plasma host-event limiter regression (PR #728 adaptation).

SYNTHETIC: deterministic scenarios with an injected monotonic clock and the
real ``canopy_core.host_events.HostEvents`` bus. No Qt instance, compiled
bridge, desktop session, screen reader, transport or visual acceptance is
claimed. The tests prove bounded/live behavior of the native Python seam:
sustained dispatches past 64, same-tick bursts with truthful deferred
outcomes, no background flush when the limiter is exhausted and no further
events arrive, and no loss of legitimate state or catalog refresh.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import canopy_core.host_events as events
from canopy_core.host_events import (
    BUCKET_CAPACITY,
    BUCKET_REFILL_MS,
    HostEventError,
    OUTCOME_HISTORY_MAX,
    REFRESH_FINGERPRINT_MAX,
    TOPICS,
    HostEvents,
)

SOURCE = (Path(__file__).resolve().parents[1] /
          "canopy_core" / "host_events.py")
CAPABILITIES = "capabilities.report"
CATALOG = "app.catalog.changed"


class Clock:
    """Injected monotonic clock in milliseconds; no sleeping or polling."""

    def __init__(self, now=0):
        self.ms = now

    def __call__(self):
        return self.ms

    def advance(self, ms):
        self.ms += ms


def bus(clock, topic=CAPABILITIES, seen=None):
    observed = [] if seen is None else seen
    callback = observed.append
    instance = HostEvents({topic: [callback]}, clock=clock)
    instance.subscribe(topic, callback)
    return instance, observed


class NativeHostEventLimiterTests(unittest.TestCase):
    def test_source_carries_bounded_limiter_without_wakeup(self):
        code = SOURCE.read_text(encoding="utf-8")
        self.assertEqual(
            (BUCKET_CAPACITY, BUCKET_REFILL_MS,
             OUTCOME_HISTORY_MAX, REFRESH_FINGERPRINT_MAX),
            (16, 1000, 16, 4))
        for marker in ("_refill", "_take", "_flush_pending", "_now",
                       "refresh_pending", "catalog-refresh-pending",
                       "catalog-refresh-coalesced", "-deferred",
                       "deque(maxlen=OUTCOME_HISTORY_MAX)",
                       "deque(maxlen=REFRESH_FINGERPRINT_MAX)"):
            with self.subTest(marker=marker):
                self.assertIn(marker, code)
        for forbidden in ("QTimer", "Thread(", "sleep(", "poll(",
                          "while True", "for (;;)", "import socket",
                          "importlib", "asyncio", "subprocess"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)
        self.assertEqual(TOPICS, frozenset({
            CATALOG, "window.state.changed", "session.state.changed",
            CAPABILITIES}))
        self.assertIn("outcome: str", code)

    def test_200_spaced_valid_dispatches_continue_past_64(self):
        clock = Clock()
        instance, seen = bus(clock)
        outcomes = []
        for index in range(200):
            clock.advance(BUCKET_REFILL_MS)
            topic = ("window.state.changed" if index % 4 == 0
                     else CAPABILITIES)
            payload = ({"state": "active"}
                       if topic == "window.state.changed" else
                       {"network_connected": True, "volume_percent": index % 101})
            result = instance.emit(topic, payload)
            self.assertEqual((result.delivered, result.callback_failures),
                             (0 if topic != CAPABILITIES else 1, 0))
            outcomes.append(result.outcome)
        stats = instance.limiter_stats
        self.assertEqual(len(seen), 150)
        self.assertEqual(stats["dispatch_count"], 200)
        self.assertEqual(stats["accepted"], 200)
        self.assertEqual(stats["rejected"], 0)
        self.assertEqual(stats["outcome_count"], OUTCOME_HISTORY_MAX)
        self.assertLessEqual(stats["fingerprint_count"],
                             REFRESH_FINGERPRINT_MAX)
        self.assertTrue(all(outcome.endswith("-deferred") is False
                            for outcome in outcomes),
                        "a spaced valid dispatch must not be deferred")
        instance.close()

    def test_same_tick_burst_commits_every_state_with_truthful_outcomes(self):
        clock = Clock()
        instance, seen = bus(clock)
        outcomes = []
        for _ in range(200):
            result = instance.emit(CAPABILITIES, {"network_connected": True})
            self.assertEqual((result.delivered, result.callback_failures),
                             (1, 0))
            outcomes.append(result.outcome)
        self.assertEqual(len(seen), 200)
        self.assertEqual(outcomes.count("quick-controls-applied"), 16)
        self.assertEqual(outcomes.count("quick-controls-applied-deferred"),
                         184)
        self.assertEqual(instance.limiter_stats["tokens"], 0)
        self.assertEqual(instance.limiter_stats["rejected"], 0)
        self.assertEqual(instance.outcome_history,
                         ("quick-controls-applied-deferred",) * 16)
        self.assertFalse(instance.refresh_pending)
        instance.close()

    def test_committed_window_and_session_state_are_never_deferred_false(self):
        clock = Clock()
        callbacks = []
        callback = callbacks.append
        allowed = {topic: [callback] for topic in (
            "window.state.changed", "session.state.changed", CAPABILITIES)}
        instance = HostEvents(allowed, clock=clock)
        for topic in allowed:
            instance.subscribe(topic, callback)
        for _ in range(BUCKET_CAPACITY):
            self.assertEqual(instance.emit(
                CAPABILITIES, {"network_connected": True}).delivered, 1)
        window = instance.emit("window.state.changed", {"state": "active"})
        session = instance.emit("session.state.changed", {"state": "active"})
        self.assertEqual((window.delivered, session.delivered), (1, 1))
        self.assertEqual(window.outcome, "window-applied-deferred")
        self.assertEqual(session.outcome, "session-observed-deferred")
        self.assertEqual(instance.limiter_stats["rejected"], 0)
        instance.close()

    def test_exhausted_limiter_and_no_further_events_stays_latched(self):
        """No clock-driven wakeup: only the next real dispatch flushes."""
        clock = Clock()
        instance, seen = bus(clock)
        for _ in range(BUCKET_CAPACITY):
            instance.emit(CAPABILITIES, {"network_connected": True})
        latched = instance.emit(CATALOG, {"count": 1})
        self.assertEqual(latched.outcome, "catalog-refresh-pending")
        self.assertTrue(instance.refresh_pending)
        self.assertEqual(instance.refresh_requests, 0)
        before = dict(instance.limiter_stats)

        clock.advance(10 * BUCKET_REFILL_MS)
        self.assertEqual(instance.refresh_requests, before["refresh_requests"])
        self.assertTrue(instance.refresh_pending)
        self.assertEqual(instance.limiter_stats["dispatch_count"],
                         before["dispatch_count"])

        flushed = instance.emit(CAPABILITIES, {"network_connected": False})
        self.assertEqual((flushed.delivered, flushed.outcome),
                         (1, "quick-controls-applied"))
        self.assertEqual(instance.refresh_requests, 1)
        self.assertFalse(instance.refresh_pending)
        self.assertEqual(len(seen), BUCKET_CAPACITY + 1)
        instance.close()

    def test_catalog_duplicate_coalescing_and_bounded_rings(self):
        clock = Clock()
        instance, _ = bus(clock, CATALOG)
        token = {"count": 1}
        for _ in range(10):
            result = instance.emit(CATALOG, token)
            self.assertEqual(result.delivered, 1)
        self.assertEqual(instance.refresh_requests, 1)
        self.assertEqual(result.outcome, "catalog-refresh-coalesced")
        self.assertEqual(instance.limiter_stats["fingerprint_count"], 1)
        for tick in range(1, 101):
            clock.advance(BUCKET_REFILL_MS)
            instance.emit(CATALOG, {"count": tick + 1})
            self.assertLessEqual(instance.limiter_stats["outcome_count"], 16)
            self.assertLessEqual(instance.limiter_stats["fingerprint_count"], 4)
        self.assertEqual(instance.refresh_requests, 101)
        self.assertEqual(instance.limiter_stats["fingerprint_count"], 4)
        self.assertEqual(len(instance.outcome_history), 16)
        instance.close()

    def test_17_valid_events_per_tick_flood_keeps_every_refresh(self):
        """PR #728 starvation scenario on the native bus (SYNTHETIC)."""
        clock = Clock()
        instance, seen = bus(clock)
        for tick in range(1, 21):
            clock.advance(BUCKET_REFILL_MS)
            for index in range(17):
                if index < 16:
                    topic = CAPABILITIES
                    payload = {"volume_percent": index, "count": tick}
                else:
                    topic = CATALOG
                    payload = {"count": tick}
                result = instance.emit(topic, payload)
                self.assertEqual((result.delivered, result.callback_failures),
                                 (1 if topic == CAPABILITIES else 0, 0))
            self.assertTrue(instance.refresh_pending,
                            "fresh catalog refresh lost at tick %d" % tick)
            self.assertEqual(instance.limiter_stats["tokens"], 0)
            self.assertLessEqual(instance.limiter_stats["fingerprint_count"], 4)
        self.assertEqual(instance.refresh_requests, 19)
        clock.advance(BUCKET_REFILL_MS)
        trigger = instance.emit(CAPABILITIES, {"volume_percent": 5})
        self.assertEqual(trigger.outcome, "quick-controls-applied")
        self.assertEqual(instance.refresh_requests, 20)
        self.assertFalse(instance.refresh_pending)
        self.assertEqual(instance.limiter_stats["dispatch_count"],
                         20 * 17 + 1)
        self.assertEqual(instance.limiter_stats["rejected"], 0)
        instance.close()

    def test_malformed_traffic_is_rejected_without_spending_a_token(self):
        clock = Clock()
        instance, seen = bus(clock)
        # The bus owns envelope/payload bounds; topic-specific claims stay
        # with their trusted consumer controllers. Only bus-level refusals
        # are exercised here.
        bad = (
            ("wifi.scan.changed", {"source": "host-events"}),
            (CATALOG, {"user_password": "SENSITIVE"}),
            (CAPABILITIES, {"__proto__": 1}),
            (CAPABILITIES, {"nested": []}),
            (CAPABILITIES, {"value": float("nan")}),
        )
        for topic, payload in bad:
            with self.subTest(topic=topic, payload=sorted(payload)):
                with self.assertRaises(HostEventError):
                    instance.emit(topic, payload)
        stats = instance.limiter_stats
        self.assertEqual((stats["tokens"], stats["rejected"],
                          stats["dispatch_count"], instance.refresh_requests),
                         (16, 5, 0, 0))
        self.assertFalse(instance.refresh_pending)
        self.assertEqual(seen, [])
        self.assertTrue(all("SENSITIVE" not in o
                            for o in instance.outcome_history))
        self.assertEqual(instance.emit(CAPABILITIES,
                                       {"network_connected": True}).delivered,
                         1)
        instance.close()

    def test_backwards_clock_never_grants_tokens(self):
        class BackwardsClock:
            def __init__(self):
                self.calls = 0

            def __call__(self):
                self.calls += 1
                return 0 if self.calls == 1 else -5000

        clock = BackwardsClock()
        instance, _ = bus(clock)
        for index in range(20):
            result = instance.emit(CAPABILITIES, {"count": index})
            self.assertEqual(result.delivered, 1)
            expected = ("quick-controls-applied" if index < 16 else
                        "quick-controls-applied-deferred")
            self.assertEqual(result.outcome, expected)
        self.assertEqual(instance.limiter_stats["tokens"], 0)
        self.assertEqual(instance.limiter_stats["rejected"], 0)
        instance.close()

    def test_injected_clock_validation_and_source_no_new_topics(self):
        with self.assertRaises(HostEventError):
            HostEvents({}, clock="not-callable")
        with self.assertRaises(HostEventError):
            HostEvents({}, clock=lambda: "not-numeric")
        code = SOURCE.read_text(encoding="utf-8")
        literals = set(re.findall(r'"([a-z]+\.[a-z.]+)"', code))
        self.assertEqual(literals & set(TOPICS), set(TOPICS))
        self.assertEqual(events.PROTOCOL_VERSION, 2)


if __name__ == "__main__":
    unittest.main()
