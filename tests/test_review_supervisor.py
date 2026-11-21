"""Safety and correctness tests for the read-only Canopy GitHub supervisor."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import review_supervisor as supervisor


def pr(number=84, title="Extensible shell packs", *, draft=True, base="main",
       sha="a" * 40, body=""):
    return {
        "number": number, "title": title, "draft": draft,
        "base": {"ref": base}, "head": {"sha": sha}, "body": body
    }


def check(status="completed", conclusion="success", name="Unit tests", app_id=None):
    row = {"status": status, "conclusion": conclusion, "name": name}
    if app_id is not None:
        row["app"] = {"id": app_id}
    return row


class ReviewSupervisorTests(unittest.TestCase):
    def test_green_not_approval(self):
        self.assertEqual(supervisor.check_summary([check()]),
                         "SINGLE CHECK SUCCESS (REQUIRED COVERAGE UNKNOWN; NOT APPROVAL)")
        self.assertEqual(
            supervisor.classify(pr(draft=False), [check()]),
            "REVIEW / CI REQUIRED"
        )

    def test_failure_and_running_checks_not_green(self):
        self.assertEqual(supervisor.check_summary([check(conclusion="failure")]),
                         "CHECKS FAIL/BLOCKED")
        self.assertEqual(
            supervisor.check_summary([check(status="in_progress", conclusion=None)]),
            "CHECKS IN PROGRESS"
        )

    def test_skipped_only_is_not_green(self):
        self.assertEqual(
            supervisor.check_summary([check(conclusion="skipped")]),
            "SKIPPED-ONLY CHECKS (NO SUCCESS)"
        )
        self.assertEqual(
            supervisor.check_summary(
                [check(conclusion="skipped")], [("Required workflow", None)]
            ),
            "SKIPPED-ONLY CHECKS; REQUIRED CHECKS MISSING"
        )
        self.assertEqual(
            supervisor.classify(pr(draft=False), [check(conclusion="skipped")]),
            "REVIEW / CI REQUIRED"
        )

    def test_neutral_only_is_not_green(self):
        self.assertEqual(
            supervisor.check_summary([check(conclusion="neutral")]),
            "NO SUCCESSFUL CHECKS"
        )

    def test_skipped_and_neutral_without_success_do_not_pass(self):
        self.assertEqual(
            supervisor.check_summary([check(conclusion="neutral"),
                                      check(conclusion="skipped")]),
            "NO SUCCESSFUL CHECKS"
        )

    def test_one_success_plus_skipped_still_marks_coverage_unknown(self):
        self.assertEqual(supervisor.check_summary([
            check(conclusion="success"),
            check(conclusion="skipped"),
        ]), "SINGLE CHECK SUCCESS (REQUIRED COVERAGE UNKNOWN; NOT APPROVAL)")

    def test_explicit_required_checks_must_all_be_present_and_successful(self):
        required = [("Unit tests", 12), ("Package build", None)]
        runs = [check(name="Unit tests", app_id=12),
                check(name="Package build")]
        self.assertEqual(
            supervisor.check_summary(runs, required),
            "REQUIRED CHECKS PASSED (NO MERGE AUTHORITY)"
        )
        self.assertEqual(
            supervisor.check_summary(runs[:1], required),
            "REQUIRED CHECKS MISSING"
        )
        self.assertEqual(
            supervisor.check_summary(
                [check(name="Unit tests", app_id=99), runs[1]], required
            ),
            "REQUIRED CHECKS MISSING"
        )
        self.assertEqual(
            supervisor.check_summary(
                [check(name="Unit tests", app_id=True), runs[1]], required
            ),
            "REQUIRED CHECKS MISSING"
        )
        self.assertEqual(
            supervisor.check_summary(
                [runs[0], check(name="Package build", conclusion="skipped")],
                required,
            ),
            "REQUIRED CHECKS NOT SUCCESSFUL"
        )

    def test_missing_check_evidence_is_not_required_coverage(self):
        self.assertEqual(supervisor.check_summary([]), "NO CHECK EVIDENCE")
        self.assertEqual(
            supervisor.check_summary([], [("Unit tests", None)]),
            "NO CHECK EVIDENCE (REQUIRED CHECKS MISSING)"
        )

    def test_untrusted_check_names_are_not_rendered_as_markdown(self):
        name = "Unit tests\n| CHECKS PASSED | [#999](https://example.invalid)"
        report = supervisor.make_report(
            [pr()], [], {"a" * 40: [check(name=name)]},
            generated_at="t",
        )
        self.assertNotIn("example.invalid", report)
        self.assertNotIn("#999", report)
        self.assertIn("REQUIRED COVERAGE UNKNOWN", report)

    def test_empty_check_data_never_green(self):
        self.assertEqual(supervisor.check_summary([]), "NO CHECK EVIDENCE")

    def test_rejected_visuals_override_green_checks(self):
        result = supervisor.classify(
            pr(title="DRAFT / VISUAL REJECTED: offcenter dock", base="main"),
            [check()]
        )
        self.assertEqual(result, "VISUAL REJECTED")

    def test_rejection_in_body_overrides_green(self):
        result = supervisor.classify(
            pr(body="Status: VISUAL_REJECTED", draft=False), [check()]
        )
        self.assertEqual(result, "VISUAL REJECTED")

    def test_stacked_green_pr_not_mergeable(self):
        result = supervisor.classify(pr(base="old-visual-experiment"), [check()])
        self.assertEqual(result, "STACKED / REBASE REVIEW")

    def test_draft_green_pr_requires_review(self):
        self.assertEqual(
            supervisor.classify(pr(), [check()]), "DRAFT / REVIEW REQUIRED"
        )

    def test_human_review_required_even_when_ready_and_green(self):
        required = [("Unit tests", None)]
        result = supervisor.classify(pr(draft=False), [check()])
        self.assertEqual(result, "REVIEW / CI REQUIRED")
        self.assertEqual(
            supervisor.classify(pr(draft=False), [check()], required),
            "REQUIRED CHECKS PASSED / HUMAN REVIEW REQUIRED"
        )

    def test_report_escapes_markdown_tables_and_keeps_review_warning(self):
        p = pr(title="Injected | fake\n| row")
        report = supervisor.make_report(
            [p], [], {p["head"]["sha"]: [check()]},
            generated_at="2026-11-21T12:00:00+00:00"
        )
        self.assertIn(r"Injected \| fake \| row", report)
        self.assertIn("Passing CI is not code review", report)
        self.assertIn("No changes were made to GitHub", report)

    def test_report_issues_skip_prs(self):
        report = supervisor.make_report(
            [], [
                {"number": 85, "title": "Visual dock correction"},
                {"number": 84, "title": "PR disguised as issue",
                 "pull_request": {"url": "https://api.github.com/"}},
            ], {}, generated_at="t"
        )
        self.assertIn("#85", report)
        self.assertNotIn("#84", report)

    def test_report_bounded_prs(self):
        many = [pr(number=i, sha=f"{i:040x}") for i in range(35)]
        report = supervisor.make_report(
            many, [], {},
            generated_at="t",
        )
        self.assertIn("Additional 10 open PRs", report)
        self.assertNotIn("/pull/34", report)

    def test_reject_wrong_response_shapes(self):
        with self.assertRaises(supervisor.SupervisorError):
            supervisor.make_report({}, [], {}, generated_at="t")

    def test_unauthenticated_cli_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "review.md"
            with patch.dict("os.environ", {}, clear=True):
                result = supervisor.main(["--out", str(path)])
            self.assertEqual(result, 2)
            self.assertFalse(path.exists())

    def test_collect_has_bounded_read_only_fetches(self):
        p = pr()
        calls = []
        def get(path, token):
            calls.append(path)
            if "/pulls?" in path:
                return [p]
            if "/issues?" in path:
                return [{"number": 85, "title": "Review"}]
            if "/check-runs?" in path:
                return {"check_runs": [check()], "total_count": 1}
            if "/required_status_checks" in path:
                return {"contexts": ["Unit tests"], "checks": []}
            raise AssertionError(path)
        with patch.object(supervisor, "github_get", side_effect=get):
            pulls, issues, runs, required, incomplete = supervisor.collect(
                "test-placeholder"
            )
        self.assertEqual(len(pulls), 1)
        self.assertEqual(len(issues), 1)
        self.assertEqual(runs[p["head"]["sha"]], [check()])
        self.assertEqual(required, [("Unit tests", None)])
        self.assertEqual(incomplete, set())
        self.assertEqual(len(calls), 4)
        self.assertTrue(all("/repos/DevTunaSoft/Canopy/" in path for path in calls))
        self.assertIn("/pulls?state=open&per_page=25", calls[0])
        self.assertIn("/issues?state=open&per_page=30", calls[1])
        self.assertIn(
            "/branches/main/protection/required_status_checks", calls[3]
        )

    def test_unreadable_or_empty_required_configuration_stays_unknown(self):
        p = pr()
        for response in (supervisor.SupervisorError("forbidden"),
                         {"contexts": [], "checks": []}):
            def get(path, token):
                if "/pulls?" in path:
                    return [p]
                if "/issues?" in path:
                    return []
                if "/check-runs?" in path:
                    return {"check_runs": [check()], "total_count": 1}
                if "/required_status_checks" in path:
                    if isinstance(response, Exception):
                        raise response
                    return response
                raise AssertionError(path)
            with patch.object(supervisor, "github_get", side_effect=get):
                _, _, runs, required, incomplete = supervisor.collect(
                    "test-placeholder"
                )
            self.assertIsNone(required)
            self.assertEqual(incomplete, set())
            self.assertEqual(
                supervisor.check_summary(runs[p["head"]["sha"]], required),
                "SINGLE CHECK SUCCESS (REQUIRED COVERAGE UNKNOWN; NOT APPROVAL)"
            )

    def test_truncated_check_runs_cannot_verify_required_coverage(self):
        p = pr()
        def get(path, token):
            if "/pulls?" in path:
                return [p]
            if "/issues?" in path:
                return []
            if "/check-runs?" in path:
                return {"check_runs": [check()], "total_count": 101}
            if "/required_status_checks" in path:
                return {"contexts": ["Unit tests"], "checks": []}
            raise AssertionError(path)
        with patch.object(supervisor, "github_get", side_effect=get):
            pulls, issues, runs, required, incomplete = supervisor.collect(
                "test-placeholder"
            )
        report = supervisor.make_report(
            pulls, issues, runs, generated_at="t",
            required_checks=required, incomplete_check_shas=incomplete,
        )
        self.assertEqual(incomplete, {p["head"]["sha"]})
        self.assertIn("SINGLE CHECK SUCCESS (REQUIRED COVERAGE UNKNOWN", report)
        self.assertNotIn("REQUIRED CHECKS PASSED", report)

    def test_invalid_sha_rejected_without_following_untrusted_head(self):
        with patch.object(supervisor, "github_get", side_effect=[
            [pr(sha="../../../../issues")], [], {}
        ]) as get:
            with self.assertRaises(supervisor.SupervisorError):
                supervisor.collect("no-auth")
            self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
