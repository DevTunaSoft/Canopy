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


def check(status="completed", conclusion="success"):
    return {"status": status, "conclusion": conclusion, "name": "Unit tests"}


class ReviewSupervisorTests(unittest.TestCase):
    def test_green_not_approval(self):
        self.assertEqual(supervisor.check_summary([check()]),
                         "CHECKS GREEN (coverage not verified; not approval)")
        self.assertIn("COVERAGE + HUMAN REVIEW REQUIRED",
                      supervisor.classify(pr(draft=False), [check()]))

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
            "NO SUCCESSFUL CHECKS"
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

    def test_one_real_success_still_marks_coverage_unverified(self):
        status = supervisor.check_summary([
            check(conclusion="success"),
            check(conclusion="skipped"),
        ])
        self.assertIn("coverage not verified", status)
        self.assertNotIn("safe to merge", status.lower())

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
        result = supervisor.classify(pr(draft=False), [check()])
        self.assertEqual(result, "CHECKS PASSED / COVERAGE + HUMAN REVIEW REQUIRED")

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
                return {"check_runs": [check()]}
            raise AssertionError(path)
        with patch.object(supervisor, "github_get", side_effect=get):
            pulls, issues, runs = supervisor.collect("test-placeholder")
        self.assertEqual(len(pulls), 1)
        self.assertEqual(len(issues), 1)
        self.assertEqual(runs[p["head"]["sha"]], [check()])
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("/repos/DevTunaSoft/Canopy/" in path for path in calls))
        self.assertIn("/pulls?state=open&per_page=25", calls[0])
        self.assertIn("/issues?state=open&per_page=30", calls[1])

    def test_invalid_sha_rejected_without_following_untrusted_head(self):
        with patch.object(supervisor, "github_get", side_effect=[
            [pr(sha="../../../../issues")], [], {}
        ]) as get:
            with self.assertRaises(supervisor.SupervisorError):
                supervisor.collect("no-auth")
            self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
