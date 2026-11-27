"""PE-076: bounded native catalog refresh bridge over app.catalog.changed.

Targeted offline tests only. No Qt, compiled source, asset, process launch,
timer, poll, thread, VM or visual state is involved. All producer inputs are
finite synthetic temp directories; every negative control is RED on the
unfixed base tree.
"""
import tempfile
import unittest
from pathlib import Path

from canopy_core.event_trust import EventTrustBoundary, EventTrustError
from canopy_core.host_events import (
    PROTOCOL_VERSION, HostEvent,
)
from canopy_features.apps.app_launch_preview import (
    REASON_APP_UNAVAILABLE, compose_app_launch_preview,
)
from canopy_features.catalog import native_catalog_refresh as bridge_module
from canopy_features.catalog.missing_app_availability import (
    MAX_REFRESH_CYCLES, REASON_ENTRY_UNREADABLE, REASON_NOT_IN_CATALOG,
    REASON_OK, MissingAppTracker,
)
from canopy_features.launcher.catalog_search import search_catalog
from canopy_features.launcher.native_catalog_producer import (
    NativeCatalogError, produce_catalog_bytes,
)

from canopy_features.catalog.native_catalog_refresh import (
    CLAIM_BOUNDED_REFRESH, CLAIM_NO_PROCESS_LAUNCH, CLAIM_NO_TIMER,
    CLAIM_NO_VALUE_ECHO, FIXED_CLAIMS, MAX_REFRESH_EVENTS,
    OUTCOME_OK, OUTCOME_REFUSED, OUTCOME_REJECTED, OUTCOME_UNCHANGED,
    REFRESH_TOPIC, CatalogRefreshError, NativeCatalogRefreshBridge,
    RefreshReport,
)

SOURCE = object()
OTHER_SOURCE = object()
ONE = "org.example.One.desktop"
BROWSER = "org.example.Browser.desktop"
BETA = "org.example.Beta.desktop"


def write_entry(folder, name, title):
    (folder / name).write_bytes((
        "[Desktop Entry]\nType=Application\nName=%s\n"
        "Exec=/usr/bin/synthetic\nCategories=Utility;\n" % title
    ).encode("utf-8"))


def positive_facts(app_id):
    """Trusted host-supplied TryExec/read facts: all positive."""
    return {"tryexec_ok": True, "entry_readable": True}


def make_bridge(apps, tracker=None, **kwargs):
    return NativeCatalogRefreshBridge(
        apps, tracker if tracker is not None else MissingAppTracker(),
        source=SOURCE, fact_source=positive_facts, **kwargs)


class ContractTests(unittest.TestCase):
    def test_fixed_tokens_and_bounds(self):
        self.assertEqual(REFRESH_TOPIC, "app.catalog.changed")
        self.assertEqual(MAX_REFRESH_EVENTS, 64)
        self.assertEqual(len(FIXED_CLAIMS), len(set(FIXED_CLAIMS)))
        for claim in (CLAIM_BOUNDED_REFRESH, CLAIM_NO_PROCESS_LAUNCH,
                      CLAIM_NO_TIMER, CLAIM_NO_VALUE_ECHO):
            self.assertIn(claim, FIXED_CLAIMS)

    def test_no_timer_poll_or_thread_in_bridge_source(self):
        source = Path(bridge_module.__file__).read_text(encoding="utf-8")
        for token in ("threading", "sleep(", "poll(", "Timer("):
            self.assertNotIn(token, source)

    def test_hostile_constructor_arguments_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="pe076-ctor-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            for build in (
                lambda: NativeCatalogRefreshBridge(
                    apps, MissingAppTracker(), source=None,
                    fact_source=positive_facts),
                lambda: NativeCatalogRefreshBridge(
                    apps, object(), source=SOURCE, fact_source=positive_facts),
                lambda: NativeCatalogRefreshBridge(
                    apps, MissingAppTracker(), source=SOURCE,
                    fact_source=positive_facts, max_events=0),
                lambda: NativeCatalogRefreshBridge(
                    apps, MissingAppTracker(), source=SOURCE,
                    fact_source=positive_facts, producer=object()),
            ):
                with self.subTest(build=build):
                    with self.assertRaises(CatalogRefreshError):
                        build()


class RefreshTests(unittest.TestCase):
    def test_nc01_install_event_reproduces_exactly_once(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc01-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            before = produce_catalog_bytes(apps)
            calls = []

            def counting_producer(path):
                calls.append(path)
                return produce_catalog_bytes(path)

            bridge = make_bridge(apps, producer=counting_producer)
            write_entry(apps, BROWSER, "Browser")
            report = bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 2})
            self.assertEqual(len(calls), 1)
            self.assertEqual(report.producer_calls, 1)
            self.assertEqual(report.outcome, OUTCOME_OK)
            self.assertEqual(report.installed_count, 2)
            self.assertEqual(report.removed_count, 0)
            self.assertIsInstance(report, RefreshReport)
            self.assertEqual(bridge.snapshot(), produce_catalog_bytes(apps))
            self.assertNotEqual(bridge.snapshot(), before)

    def test_nc01_duplicate_event_without_source_change_is_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc01b-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            first = bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            second = bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            self.assertEqual(first.outcome, OUTCOME_OK)
            self.assertEqual(second.outcome, OUTCOME_UNCHANGED)
            self.assertEqual(second.installed_count, 0)
            self.assertEqual(second.removed_count, 0)
            self.assertEqual(bridge.producer_calls, 2)

    def test_nc02_removal_drops_app_and_denies_launch(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc02-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            write_entry(apps, BROWSER, "Browser")
            bridge = make_bridge(apps)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 2})
            stale_catalog = bridge.catalog()
            self.assertEqual(bridge.state(BROWSER).reason, REASON_OK)
            self.assertTrue(bridge.state(BROWSER).launch_permitted)

            (apps / BROWSER).unlink()
            report = bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            self.assertEqual(report.removed_count, 1)
            state = bridge.state(BROWSER)
            self.assertEqual(state.reason, REASON_NOT_IN_CATALOG)
            self.assertFalse(state.launch_permitted)

            self.assertEqual(
                [hit.app_id for hit in search_catalog("Browser", bridge.catalog())],
                [])
            # A stale host snapshot that still holds the removed row is also
            # denied: availability, not the cached catalog, gates launch.
            stale_rows = [(row.app_id, row.title) for row in stale_catalog.rows]
            preview = compose_app_launch_preview(
                "Browser", stale_rows, allowed_app_ids=(BROWSER,),
                availability=state)
            self.assertEqual(preview.reason, REASON_APP_UNAVAILABLE)

    def test_nc03_stale_snapshot_cannot_be_observed_after_refresh(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc03-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            write_entry(apps, BROWSER, "Browser")
            bridge = make_bridge(apps)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 2})
            stale = bridge.catalog()
            self.assertEqual(
                [hit.app_id for hit in search_catalog("Browser", stale)],
                [BROWSER])
            (apps / BROWSER).unlink()
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            self.assertEqual(
                [hit.app_id for hit in search_catalog("Browser", stale)],
                [BROWSER])
            self.assertEqual(
                [hit.app_id for hit in search_catalog("Browser", bridge.catalog())],
                [])
            self.assertNotIn(BROWSER.encode("utf-8"), bridge.snapshot())

    def test_nc04_authoritative_observation_resets_exhaustion(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc04-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            tracker = MissingAppTracker()
            for _ in range(MAX_REFRESH_CYCLES):
                tracker.refresh(ONE, lambda _: False)
            before = tracker.state(ONE)
            self.assertEqual(before.refresh_count, MAX_REFRESH_CYCLES)
            self.assertFalse(before.launch_permitted)
            bridge = make_bridge(apps, tracker=tracker)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            after = bridge.state(ONE)
            self.assertEqual(after.reason, REASON_OK)
            self.assertEqual(after.refresh_count, 0)
            self.assertEqual(after.probe_calls, 0)
            self.assertTrue(after.launch_permitted)

    def test_catalog_presence_alone_never_grants_launch(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nofacts-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = NativeCatalogRefreshBridge(
                apps, MissingAppTracker(), source=SOURCE)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            self.assertFalse(bridge.state(ONE).launch_permitted)
            self.assertEqual(bridge.state(ONE).reason, REASON_ENTRY_UNREADABLE)

    def test_unknown_fact_source_fails_closed_without_leaking_exception(self):
        with tempfile.TemporaryDirectory(prefix="pe076-badfacts-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")

            def hostile(app_id):
                raise RuntimeError("host tried to read process state")

            bridge = NativeCatalogRefreshBridge(
                apps, MissingAppTracker(), source=SOURCE, fact_source=hostile)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            self.assertFalse(bridge.state(ONE).launch_permitted)
            self.assertEqual(bridge.state(ONE).reason, REASON_ENTRY_UNREADABLE)


class RejectionTests(unittest.TestCase):
    def test_nc07_untrusted_source_topic_and_replay_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc07-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            wire = bridge.snapshot()
            before_probe_calls = bridge.state(ONE).probe_calls
            before_refresh = bridge.state(ONE).refresh_count

            with self.assertRaises(EventTrustError):
                bridge.ingest(OTHER_SOURCE, REFRESH_TOPIC, {"item_count": 2})
            self.assertEqual(bridge.boundary.last_rejection, "UNTRUSTED_SOURCE")
            with self.assertRaises(EventTrustError):
                bridge.ingest(SOURCE, "window.state.changed", {"state": "x"})
            self.assertEqual(bridge.boundary.last_rejection, "UNSUPPORTED_TOPIC")

            replay = HostEvent(PROTOCOL_VERSION, REFRESH_TOPIC, 1,
                               (("item_count", 2),))
            report = bridge.apply(replay)
            self.assertEqual(report.outcome, OUTCOME_REJECTED)
            self.assertEqual(bridge.last_rejection, "REPLAYED_SEQUENCE")
            self.assertEqual(bridge.rejection_count, 3)

            self.assertEqual(bridge.snapshot(), wire)
            self.assertEqual(bridge.state(ONE).probe_calls, before_probe_calls)
            self.assertEqual(bridge.state(ONE).refresh_count, before_refresh)

    def test_nc07_malformed_and_oversized_payloads_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc07b-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            with self.assertRaises(EventTrustError):
                bridge.ingest(SOURCE, REFRESH_TOPIC, {"nested": [1, 2]})
            self.assertEqual(bridge.boundary.last_rejection, "INVALID_PAYLOAD")
            with self.assertRaises(EventTrustError):
                bridge.ingest(SOURCE, REFRESH_TOPIC, dict(
                    (chr(ord("a") + index), "x" * 300) for index in range(8)))
            self.assertEqual(bridge.boundary.last_rejection, "OVERSIZED_EVENT")
            self.assertIsNone(bridge.snapshot())
            self.assertEqual(bridge.producer_calls, 0)

    def test_hostile_event_envelope_is_rejected_without_refresh(self):
        with tempfile.TemporaryDirectory(prefix="pe076-envelope-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            for event in (object(),
                          HostEvent(PROTOCOL_VERSION + 1, REFRESH_TOPIC, 1, ()),
                          HostEvent(PROTOCOL_VERSION, "window.state.changed", 1, ())):
                with self.subTest(event=event):
                    report = bridge.apply(event)
                    self.assertEqual(report.outcome, OUTCOME_REJECTED)
            self.assertIsNone(bridge.snapshot())
            self.assertEqual(bridge.producer_calls, 0)

    def test_event_budget_reconciles_at_epoch_boundary(self):
        with tempfile.TemporaryDirectory(prefix="pe076-epoch-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps, max_events=2)
            self.assertEqual(bridge.ingest(SOURCE, REFRESH_TOPIC, {}).outcome,
                             OUTCOME_OK)
            self.assertEqual(bridge.ingest(SOURCE, REFRESH_TOPIC, {}).outcome,
                             OUTCOME_UNCHANGED)
            third = bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            self.assertEqual(third.outcome, OUTCOME_UNCHANGED)
            self.assertEqual(third.producer_calls, 1)
            self.assertEqual(bridge.producer_calls, 3)
            self.assertEqual(bridge.epoch_events, 1)
            self.assertEqual(bridge.reconciliations, 1)
            self.assertTrue(bridge.connected())
            self.assertIsNone(bridge.last_rejection)

    def test_new_authoritative_catalog_is_reconciled_after_max_events(self):
        with tempfile.TemporaryDirectory(prefix="pe076-past-limit-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            for index in range(MAX_REFRESH_EVENTS):
                expected = OUTCOME_OK if index == 0 else OUTCOME_UNCHANGED
                self.assertEqual(
                    bridge.ingest(SOURCE, REFRESH_TOPIC, {}).outcome,
                    expected)
            self.assertEqual(bridge.event_count, MAX_REFRESH_EVENTS)
            self.assertEqual(bridge.epoch_events, MAX_REFRESH_EVENTS)
            self.assertEqual(bridge.reconciliations, 0)
            write_entry(apps, BETA, "Beta")
            after = bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            self.assertEqual(after.outcome, OUTCOME_OK)
            self.assertEqual(after.installed_count, 1)
            self.assertEqual(after.producer_calls, 1)
            self.assertEqual(bridge.producer_calls, MAX_REFRESH_EVENTS + 1)
            self.assertEqual(bridge.event_count, MAX_REFRESH_EVENTS + 1)
            self.assertEqual(bridge.epoch_events, 1)
            self.assertEqual(bridge.reconciliations, 1)
            self.assertTrue(bridge.connected())
            self.assertTrue(bridge.state(BETA).launch_permitted)
            wire = bridge.snapshot()
            self.assertIsNotNone(wire)
            self.assertIn(BETA.encode("utf-8"), wire)
            self.assertEqual(wire, produce_catalog_bytes(apps))
            self.assertEqual(bridge.reports()[-1].outcome, OUTCOME_OK)
            self.assertLessEqual(len(bridge.reports()),
                                 bridge_module.MAX_REPORT_HISTORY)

    def test_bad_events_after_boundary_do_not_spend_a_producer_call(self):
        with tempfile.TemporaryDirectory(prefix="pe076-limit-negative-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            for _ in range(MAX_REFRESH_EVENTS):
                bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            calls = bridge.producer_calls
            with self.assertRaises(EventTrustError):
                bridge.ingest(OTHER_SOURCE, REFRESH_TOPIC, {})
            replay = HostEvent(PROTOCOL_VERSION, REFRESH_TOPIC, 1, ())
            self.assertEqual(bridge.apply(replay).outcome, OUTCOME_REJECTED)
            with self.assertRaises(EventTrustError):
                bridge.ingest(SOURCE, "window.state.changed", {"state": "x"})
            self.assertEqual(bridge.producer_calls, calls)
            self.assertEqual(bridge.epoch_events, MAX_REFRESH_EVENTS)
            self.assertEqual(bridge.reconciliations, 0)
            self.assertEqual(bridge.event_count, MAX_REFRESH_EVENTS)
            self.assertEqual(bridge.snapshot(), produce_catalog_bytes(apps))

    def test_refused_snapshot_at_boundary_still_reconciles(self):
        with tempfile.TemporaryDirectory(prefix="pe076-refusal-epoch-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            calls = []

            def sometimes_broken(path):
                calls.append(path)
                if len(calls) == 3:
                    return b"not-a-catalog-line\n"
                return produce_catalog_bytes(path)

            bridge = make_bridge(apps, max_events=2,
                                 producer=sometimes_broken)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            refused = bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            self.assertEqual(refused.outcome, OUTCOME_REFUSED)
            self.assertEqual(bridge.epoch_events, 1)
            self.assertEqual(bridge.reconciliations, 1)
            self.assertEqual(bridge.snapshot(), produce_catalog_bytes(apps))
            self.assertEqual(
                bridge.ingest(SOURCE, REFRESH_TOPIC, {}).outcome,
                OUTCOME_UNCHANGED)
            self.assertEqual(bridge.producer_calls, 4)

    def test_close_rejects_later_events(self):
        with tempfile.TemporaryDirectory(prefix="pe076-close-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            bridge.close()
            with self.assertRaises(EventTrustError):
                bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            self.assertEqual(bridge.boundary.last_rejection, "CLOSED")


class FailureAtomicityTests(unittest.TestCase):
    def test_nc08_hostile_entry_keeps_previous_wire_byte_identical(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc08-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            wire = bridge.snapshot()
            state = bridge.state(ONE)
            before_refresh = state.refresh_count

            # A hostile desktop entry with a valid id refuses the whole
            # produce; no partial bytes and no availability change.
            (apps / "org.example.Bad.desktop").write_bytes(
                b"not a desktop entry\n")
            report = bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 2})
            self.assertEqual(report.outcome, OUTCOME_REFUSED)
            self.assertEqual(report.producer_calls, 1)
            self.assertEqual(bridge.snapshot(), wire)
            self.assertEqual(bridge.state(ONE).refresh_count, before_refresh)
            self.assertTrue(bridge.state(ONE).launch_permitted)

            # An oversized entry is refused the same way, after the bad entry
            # is removed so the source itself is otherwise valid.
            (apps / "org.example.Bad.desktop").unlink()
            with self.assertRaises(NativeCatalogError):
                produce_catalog_bytes(apps, max_file_bytes=8)
            report = bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1},
                                   max_file_bytes=8)
            self.assertEqual(report.outcome, OUTCOME_REFUSED)
            self.assertEqual(bridge.snapshot(), wire)

    def test_nc09_diagnostics_never_echo_application_text(self):
        with tempfile.TemporaryDirectory(prefix="pe076-nc09-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            report = bridge.ingest(SOURCE, REFRESH_TOPIC, {"item_count": 1})
            refused = bridge.ingest(SOURCE, REFRESH_TOPIC, {},
                                    max_file_bytes=4)

            for record in (report.to_dict(), refused.to_dict(),
                           bridge.state(ONE).to_dict()):
                text = repr(record)
                for marker in (ONE, "example", "desktop", "synthetic",
                               "usr", "bin"):
                    self.assertNotIn(marker, text)
            self.assertEqual(set(report.to_dict()), {
                "outcome", "sequence", "producer_calls", "installed_count",
                "removed_count", "snapshot_bytes", "claims",
            })
            self.assertEqual(report.claims, FIXED_CLAIMS)

    def test_report_history_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix="pe076-history-") as tmp:
            apps = Path(tmp) / "applications"
            apps.mkdir()
            write_entry(apps, ONE, "One")
            bridge = make_bridge(apps)
            for _ in range(MAX_REFRESH_EVENTS + 3):
                bridge.ingest(SOURCE, REFRESH_TOPIC, {})
            self.assertLessEqual(len(bridge.reports()), bridge_module.MAX_REPORT_HISTORY)
            self.assertTrue(all(isinstance(r, RefreshReport) for r in bridge.reports()))


if __name__ == "__main__":
    unittest.main()
