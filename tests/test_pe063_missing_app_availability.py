"""PE-063: bounded, fail-closed missing-application availability contract.

Targeted offline tests only. No process launch, filesystem walk, Qt, asset or
visual state is involved.
"""
import json
import unittest

from canopy_features.catalog.missing_app_availability import (
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_UNBOUNDED_REFRESH,
    CLAIM_NO_VALUE_ECHO,
    CLAIM_STABLE_UNAVAILABLE,
    FIXED_CLAIMS,
    FIXED_REASONS,
    MAX_REFRESH_ATTEMPTS,
    MAX_REFRESH_CYCLES,
    MAX_TRACKED_APPS,
    REQUIRED_CONFIRMATIONS,
    REASON_ENTRY_UNREADABLE,
    REASON_EXHAUSTED,
    REASON_INVALID_INPUT,
    REASON_NOT_IN_CATALOG,
    REASON_OK,
    REASON_PROBE_FAILED,
    REASON_TRYEXEC_FAILED,
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    AppAvailability,
    MissingAppError,
    MissingAppTracker,
    classify_missing_app,
)

MISSING = "org.example.Missing.desktop"
PRESENT = "org.example.Present.desktop"


def facts(*, in_catalog=True, tryexec_ok=True, entry_readable=True):
    return {
        "in_catalog": in_catalog,
        "tryexec_ok": tryexec_ok,
        "entry_readable": entry_readable,
    }


class FixedContractTests(unittest.TestCase):
    def test_status_reason_and_claim_sets_are_fixed(self):
        self.assertEqual(STATUS_UNAVAILABLE, "unavailable")
        self.assertEqual(STATUS_AVAILABLE, "available")
        self.assertEqual(REASON_OK, "ok")
        self.assertIsInstance(FIXED_REASONS, tuple)
        for reason in (REASON_OK, REASON_NOT_IN_CATALOG, REASON_TRYEXEC_FAILED,
                       REASON_ENTRY_UNREADABLE, REASON_PROBE_FAILED,
                       REASON_EXHAUSTED, REASON_INVALID_INPUT):
            self.assertIn(reason, FIXED_REASONS)
        self.assertEqual(len(FIXED_REASONS), len(set(FIXED_REASONS)))
        for claim in (CLAIM_NO_PROCESS_LAUNCH, CLAIM_NO_VALUE_ECHO,
                      CLAIM_NO_UNBOUNDED_REFRESH, CLAIM_STABLE_UNAVAILABLE):
            self.assertIn(claim, FIXED_CLAIMS)

    def test_unknown_app_is_stably_unavailable_with_no_launch_permission(self):
        state = MissingAppTracker().state(MISSING)
        self.assertIsInstance(state, AppAvailability)
        self.assertEqual(state.status, STATUS_UNAVAILABLE)
        self.assertEqual(state.reason, REASON_NOT_IN_CATALOG)
        self.assertFalse(state.launch_permitted)
        self.assertTrue(state.unavailable)
        self.assertEqual(state.claims, FIXED_CLAIMS)
        self.assertEqual(state.refresh_count, 0)
        self.assertEqual(state.probe_calls, 0)

    def test_diagnostics_never_echo_application_text(self):
        payload = json.dumps(MissingAppTracker().state(MISSING).to_dict())
        for marker in (MISSING, "example", "desktop"):
            self.assertNotIn(marker, payload)
        self.assertEqual(set(json.loads(payload)), {
            "status", "reason", "refresh_count", "confirmations",
            "probe_calls", "launch_permitted", "claims",
        })

    def test_record_is_immutable(self):
        state = MissingAppTracker().state(MISSING)
        with self.assertRaises(Exception):
            state.status = STATUS_AVAILABLE


class ClassificationTests(unittest.TestCase):
    def test_fixed_reason_for_each_missing_source_fact(self):
        cases = (
            (facts(in_catalog=False), REASON_NOT_IN_CATALOG),
            (facts(entry_readable=False), REASON_ENTRY_UNREADABLE),
            (facts(tryexec_ok=False), REASON_TRYEXEC_FAILED),
        )
        for source, expected in cases:
            with self.subTest(expected=expected):
                state = classify_missing_app(MISSING, **source)
                self.assertEqual(state.status, STATUS_UNAVAILABLE)
                self.assertEqual(state.reason, expected)
                self.assertFalse(state.launch_permitted)

    def test_present_app_with_all_facts_positive_is_launchable(self):
        state = classify_missing_app(PRESENT, **facts())
        self.assertEqual(state.status, STATUS_AVAILABLE)
        self.assertEqual(state.reason, REASON_OK)
        self.assertTrue(state.launch_permitted)

    def test_hostile_facts_fail_closed_with_domain_error(self):
        invalid = (
            lambda: classify_missing_app(7, **facts()),
            lambda: classify_missing_app("no-suffix", **facts()),
            lambda: classify_missing_app(MISSING, in_catalog="yes"),
            lambda: classify_missing_app(MISSING, **facts(entry_readable=1)),
            lambda: classify_missing_app(MISSING, **facts(tryexec_ok=None)),
        )
        for call in invalid:
            with self.subTest(call=call):
                with self.assertRaises(MissingAppError):
                    call()


class BoundedRefreshTests(unittest.TestCase):
    def test_probe_is_capped_and_unavailable_state_is_stable(self):
        calls = []

        def always_missing(app_id):
            calls.append(app_id)
            return facts(in_catalog=False)

        tracker = MissingAppTracker()
        state = tracker.refresh(MISSING, always_missing)
        self.assertEqual(len(calls), MAX_REFRESH_ATTEMPTS)
        self.assertLessEqual(state.probe_calls, MAX_REFRESH_ATTEMPTS)
        self.assertEqual(state.status, STATUS_UNAVAILABLE)
        self.assertEqual(state.reason, REASON_NOT_IN_CATALOG)
        self.assertFalse(state.launch_permitted)
        self.assertEqual(state.refresh_count, 1)
        self.assertEqual(tracker.state(MISSING), state)

    def test_single_positive_probe_cannot_manufacture_a_launch(self):
        answers = iter((True, False, False))

        def flaky(app_id):
            return next(answers)

        state = MissingAppTracker().refresh(MISSING, flaky)
        self.assertEqual(state.status, STATUS_UNAVAILABLE)
        self.assertFalse(state.launch_permitted)
        self.assertEqual(state.confirmations, 0)

    def test_two_consecutive_positive_probes_confirm_availability(self):
        calls = []

        def installed(app_id):
            calls.append(app_id)
            return True

        state = MissingAppTracker().refresh(MISSING, installed)
        self.assertEqual(len(calls), REQUIRED_CONFIRMATIONS)
        self.assertEqual(state.status, STATUS_AVAILABLE)
        self.assertEqual(state.reason, REASON_OK)
        self.assertTrue(state.launch_permitted)

    def test_probe_exception_and_bad_shape_are_translated_not_raised(self):
        def exploding(app_id):
            raise RuntimeError("probe crashed")

        for probe in (exploding, lambda app_id: object(),
                      lambda app_id: {"in_catalog": object()}):
            with self.subTest(probe=probe):
                state = MissingAppTracker().refresh(MISSING, probe)
                self.assertEqual(state.status, STATUS_UNAVAILABLE)
                self.assertEqual(state.reason, REASON_PROBE_FAILED)
                self.assertFalse(state.launch_permitted)

    def test_refresh_cycles_are_bounded_and_exhaustion_is_fixed(self):
        tracker = MissingAppTracker()
        calls = []

        def always_missing(app_id):
            calls.append(app_id)
            return facts(in_catalog=False)

        for _ in range(MAX_REFRESH_CYCLES):
            state = tracker.refresh(MISSING, always_missing)
        self.assertEqual(state.refresh_count, MAX_REFRESH_CYCLES)
        total = len(calls)
        fenced = tracker.refresh(MISSING, always_missing)
        self.assertEqual(len(calls), total)
        self.assertEqual(fenced.status, STATUS_UNAVAILABLE)
        self.assertEqual(fenced.reason, REASON_EXHAUSTED)
        self.assertEqual(fenced.probe_calls, 0)
        self.assertFalse(fenced.launch_permitted)

    def test_bad_probe_or_bounds_fail_closed_with_domain_error(self):
        tracker = MissingAppTracker()
        with self.assertRaises(MissingAppError):
            tracker.refresh(MISSING, None)
        with self.assertRaises(MissingAppError):
            MissingAppTracker(max_refresh_attempts=0)
        with self.assertRaises(MissingAppError):
            MissingAppTracker(max_refresh_cycles=MAX_REFRESH_CYCLES + 1)

    def test_observe_is_bounded_ordered_and_does_not_mutate_caller(self):
        tracker = MissingAppTracker()
        tracker.observe(PRESENT, **facts())
        tracker.observe(MISSING, **facts(tryexec_ok=False))
        snapshot = tracker.snapshot()
        self.assertEqual([state.app_id for state in snapshot],
                         [MISSING, PRESENT])
        self.assertTrue(snapshot[0].unavailable)
        self.assertTrue(snapshot[1].launch_permitted)
        self.assertIsInstance(tracker.snapshot(), tuple)

        bounded = MissingAppTracker()
        for index in range(MAX_TRACKED_APPS):
            bounded.observe("org.example.App%04d.desktop" % index, **facts())
        with self.assertRaises(MissingAppError):
            bounded.observe("org.example.Overflow.desktop", **facts())


if __name__ == "__main__":
    unittest.main()
