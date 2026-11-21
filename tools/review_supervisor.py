#!/usr/bin/env python3
"""Read-only Canopy PR/CI supervisor. Never merges, posts, assigns or executes PR code.

Called by scheduled GitHub Actions. Its GITHUB_TOKEN has read-only scopes.
The report is a review queue; green CI is NOT a merge authorization.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OWNER_REPO = "DevTunaSoft/Canopy"
MAX_REVIEW_PRS = 25
MAX_OPEN_ISSUES = 15
REQUIRED_CHECKS_BRANCH = "main"


class SupervisorError(RuntimeError):
    """Cannot safely or correctly retrieve a review snapshot."""


def github_get(path, token):
    """Fetch from one fixed GitHub repo. Never follow input-provided URLs."""
    if not path.startswith(f"/repos/{OWNER_REPO}/") or any(
            character in path for character in ("\n", "\r", "#", "\\", " ")):
        raise SupervisorError("unsafe GitHub API path")
    url = "https://api.github.com" + path
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "canopy-readonly-supervisor",
    })
    try:
        with urlopen(request, timeout=18) as response:
            if response.status != 200:
                raise SupervisorError(f"GitHub GET failed with HTTP {response.status}")
            body = response.read(1_200_001)
            if len(body) > 1_200_000:
                raise SupervisorError("GitHub response exceeds bounded size")
            return json.loads(body.decode("utf-8"))
    except (HTTPError, URLError, OSError, UnicodeError, ValueError) as exc:
        # Do not log URL-bearing credentials, response bodies or tokens.
        raise SupervisorError(f"GitHub API retrieval failed: {type(exc).__name__}") from exc


def check_summary(checks, required_checks=None):
    """Report checks without conflating a green badge with merge authorization."""
    if not isinstance(checks, list):
        return "CHECK DATA INVALID"
    if not checks:
        if required_checks:
            return "NO CHECK EVIDENCE (REQUIRED CHECKS MISSING)"
        return "NO CHECK EVIDENCE"
    if any(not isinstance(row, dict) for row in checks):
        return "CHECK DATA INVALID"
    if any(row.get("conclusion") in ("failure", "timed_out", "cancelled", "action_required")
           for row in checks):
        return "CHECKS FAIL/BLOCKED"
    if any(row.get("status") != "completed" for row in checks):
        return "CHECKS IN PROGRESS"
    skipped_only = all(row.get("conclusion") == "skipped" for row in checks)
    if required_checks:
        missing = False
        unsuccessful = False
        for context, app_id in required_checks:
            matching = [
                row for row in checks
                if row.get("name") == context and
                (app_id is None or
                 (isinstance(row.get("app"), dict) and
                  isinstance(row["app"].get("id"), int) and
                  not isinstance(row["app"].get("id"), bool) and
                  row["app"].get("id") == app_id))
            ]
            if not matching:
                missing = True
            elif any(row.get("conclusion") != "success" for row in matching):
                unsuccessful = True
        if skipped_only:
            if missing:
                return "SKIPPED-ONLY CHECKS; REQUIRED CHECKS MISSING"
            return "SKIPPED-ONLY CHECKS (NO SUCCESS)"
        if missing:
            return "REQUIRED CHECKS MISSING"
        if unsuccessful:
            return "REQUIRED CHECKS NOT SUCCESSFUL"
        return "REQUIRED CHECKS PASSED (NO MERGE AUTHORITY)"
    if skipped_only:
        return "SKIPPED-ONLY CHECKS (NO SUCCESS)"
    successful = sum(row.get("conclusion") == "success" for row in checks)
    if successful == 1:
        return "SINGLE CHECK SUCCESS (REQUIRED COVERAGE UNKNOWN; NOT APPROVAL)"
    if successful > 1:
        return "CHECKS SUCCESSFUL (REQUIRED COVERAGE UNKNOWN; NOT APPROVAL)"
    if any(row.get("conclusion") in ("neutral", "skipped") for row in checks):
        return "NO SUCCESSFUL CHECKS"
    return "CHECKS UNKNOWN"


def classify(pr, checks, required_checks=None):
    """Present review blockers in priority order; never return 'safe to merge'."""
    title = str(pr.get("title") or "").upper()
    body = str(pr.get("body") or "").upper()
    if "VISUAL REJECTED" in title or "VISUALLY REJECTED" in title or \
            "VISUAL_REJECTED" in body:
        return "VISUAL REJECTED"
    if pr.get("base", {}).get("ref") != "main":
        return "STACKED / REBASE REVIEW"
    if pr.get("draft"):
        return "DRAFT / REVIEW REQUIRED"
    status = check_summary(checks, required_checks)
    if status.startswith("REQUIRED CHECKS PASSED"):
        return "REQUIRED CHECKS PASSED / HUMAN REVIEW REQUIRED"
    return "REVIEW / CI REQUIRED"


def safe_text(value, max_chars=140):
    """Keep untrusted issue/PR titles from injecting Markdown structure."""
    text = str(value or "").replace("|", "\\|")
    text = " ".join(text.split())
    return text[:max_chars]


def make_report(pulls, issues, checks_by_sha, *, generated_at, limit=MAX_REVIEW_PRS,
                required_checks=None, incomplete_check_shas=None):
    """Build non-authoritative review queue from exact GitHub API snapshots."""
    if not isinstance(pulls, list) or not isinstance(issues, list):
        raise SupervisorError("unexpected repository collection shape")
    lines = [
        "# Canopy read-only engineering review report",
        "",
        f"Generated UTC: {generated_at}",
        "",
        "**No changes were made to GitHub by this workflow.** "
        "Passing CI is not code review, visual approval, "
        "Linux Mint acceptance or permission to merge.",
        "",
        "## Pull requests requiring review",
        "",
        "| PR | Scope | Base | Checks | Gate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for pr in pulls[:limit]:
        if not isinstance(pr, dict):
            raise SupervisorError("unexpected pull request entry")
        sha = str(pr.get("head", {}).get("sha") or "")
        checks = checks_by_sha.get(sha, [])
        coverage = required_checks if pr.get("base", {}).get("ref") == REQUIRED_CHECKS_BRANCH \
            and sha not in (incomplete_check_shas or set()) else None
        number = pr.get("number")
        lines.append(
            f"| [#{number}](https://github.com/{OWNER_REPO}/pull/{number}) "
            f"| {safe_text(pr.get('title'))} "
            f"| {safe_text(pr.get('base', {}).get('ref'), 70)} "
            f"| {check_summary(checks, coverage)} "
            f"| {classify(pr, checks, coverage)} |"
        )
    if len(pulls) > limit:
        lines.append(f"\nAdditional {len(pulls) - limit} open PRs not individually inspected.")
    lines += ["", "## Open workstream issues", "", "| Issue | Workstream |", "| --- | --- |"]
    count = 0
    for item in issues:
        if not isinstance(item, dict):
            raise SupervisorError("unexpected issue entry")
        if "pull_request" in item:
            continue
        number = item.get("number")
        lines.append(
            f"| [#{number}](https://github.com/{OWNER_REPO}/issues/{number}) "
            f"| {safe_text(item.get('title'))} |"
        )
        count += 1
        if count >= MAX_OPEN_ISSUES:
            break
    lines += [
        "",
        "## Required human decisions",
        "",
        "- Identify a real reviewer and request review on each ready PR.",
        "- Keep visually rejected work out of main; preserve approved asset sources.",
        "- Flatten/rebase stacked PRs onto a verified main branch before considering merge.",
        "- Verify actual Qt runtime and Mint VM evidence independently of unit tests.",
        "- Never turn on automatic merge or paid AI coding without explicit authorization.",
        "",
    ]
    return "\n".join(lines)


def collect(token):
    base = f"/repos/{OWNER_REPO}"
    # Live smoke evidence: fetching 100 PRs exceeded the 1.2 MB response
    # guard. Request at most the bounded review queue, never unbounded data.
    pulls = github_get(f"{base}/pulls?state=open&per_page={MAX_REVIEW_PRS}", token)
    issues = github_get(f"{base}/issues?state=open&per_page=30", token)
    if not isinstance(pulls, list) or not isinstance(issues, list):
        raise SupervisorError("unexpected GitHub API response")
    checked = {}
    incomplete_check_shas = set()
    has_main_base = False
    for pr in pulls[:MAX_REVIEW_PRS]:
        sha = pr.get("head", {}).get("sha", "")
        if not isinstance(sha, str) or len(sha) != 40 or \
                any(c not in "0123456789abcdef" for c in sha.lower()):
            raise SupervisorError("invalid pull request head SHA")
        has_main_base |= pr.get("base", {}).get("ref") == REQUIRED_CHECKS_BRANCH
        response = github_get(
            f"{base}/commits/{sha}/check-runs?per_page=100", token
        )
        if not isinstance(response, dict) or not isinstance(response.get("check_runs"), list):
            raise SupervisorError("unexpected check-runs response")
        checked[sha] = response["check_runs"]
        total_count = response.get("total_count")
        if not isinstance(total_count, int) or isinstance(total_count, bool) or \
                total_count != len(response["check_runs"]):
            incomplete_check_shas.add(sha)
    required_checks = None
    if has_main_base:
        try:
            protection = github_get(
                f"{base}/branches/{REQUIRED_CHECKS_BRANCH}/protection/required_status_checks",
                token,
            )
        except SupervisorError:
            # The workflow token may not be allowed to read branch protection.
            # Unknown configuration must never be treated as verified coverage.
            protection = None
        if isinstance(protection, dict):
            contexts = protection.get("contexts")
            checks = protection.get("checks")
            if isinstance(contexts, list) and isinstance(checks, list):
                configured = [(name, None) for name in contexts
                              if isinstance(name, str) and name]
                valid = len(configured) == len(contexts)
                for item in checks:
                    if not isinstance(item, dict) or not isinstance(item.get("context"), str) \
                            or not item["context"]:
                        valid = False
                        break
                    app_id = item.get("app_id")
                    if app_id is not None and (not isinstance(app_id, int) or
                                               isinstance(app_id, bool)):
                        valid = False
                        break
                    configured.append((item["context"], app_id))
                if valid and configured:
                    required_checks = configured
    return pulls, issues, checked, required_checks, incomplete_check_shas


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("canopy-review-report.md"))
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("SUPERVISOR_FAIL: GITHUB_TOKEN not supplied", file=sys.stderr)
        return 2
    try:
        pulls, issues, checks, required_checks, incomplete_check_shas = collect(token)
        report = make_report(
            pulls, issues, checks,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            required_checks=required_checks,
            incomplete_check_shas=incomplete_check_shas,
        )
        args.out.write_text(report, encoding="utf-8")
    except (SupervisorError, OSError, ValueError) as exc:
        print(f"SUPERVISOR_FAIL: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"SUPERVISOR_PASS: read-only report saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
