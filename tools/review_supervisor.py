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
SUCCESS_RESULTS = frozenset({"success", "neutral", "skipped"})


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


def check_summary(checks):
    """Report checks without conflating a green badge with merge authorization."""
    if not isinstance(checks, list) or not checks:
        return "NO CHECK EVIDENCE"
    if any(not isinstance(row, dict) for row in checks):
        return "CHECK DATA INVALID"
    if any(row.get("conclusion") in ("failure", "timed_out", "cancelled", "action_required")
           for row in checks):
        return "CHECKS FAIL/BLOCKED"
    if any(row.get("status") != "completed" for row in checks):
        return "CHECKS IN PROGRESS"
    if all(row.get("conclusion") in SUCCESS_RESULTS for row in checks):
        return "CHECKS GREEN (not approval)"
    return "CHECKS UNKNOWN"


def classify(pr, checks):
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
    status = check_summary(checks)
    if status.startswith("CHECKS GREEN"):
        return "CHECKS GREEN / HUMAN REVIEW REQUIRED"
    return "REVIEW / CI REQUIRED"


def safe_text(value, max_chars=140):
    """Keep untrusted issue/PR titles from injecting Markdown structure."""
    text = str(value or "").replace("|", "\\|")
    text = " ".join(text.split())
    return text[:max_chars]


def make_report(pulls, issues, checks_by_sha, *, generated_at, limit=MAX_REVIEW_PRS):
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
        number = pr.get("number")
        lines.append(
            f"| [#{number}](https://github.com/{OWNER_REPO}/pull/{number}) "
            f"| {safe_text(pr.get('title'))} "
            f"| {safe_text(pr.get('base', {}).get('ref'), 70)} "
            f"| {check_summary(checks)} "
            f"| {classify(pr, checks)} |"
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
    pulls = github_get(f"{base}/pulls?state=open&per_page=100", token)
    issues = github_get(f"{base}/issues?state=open&per_page=100", token)
    if not isinstance(pulls, list) or not isinstance(issues, list):
        raise SupervisorError("unexpected GitHub API response")
    checked = {}
    for pr in pulls[:MAX_REVIEW_PRS]:
        sha = pr.get("head", {}).get("sha", "")
        if not isinstance(sha, str) or len(sha) != 40 or \
                any(c not in "0123456789abcdef" for c in sha.lower()):
            raise SupervisorError("invalid pull request head SHA")
        response = github_get(
            f"{base}/commits/{sha}/check-runs?per_page=100", token
        )
        if not isinstance(response, dict) or not isinstance(response.get("check_runs"), list):
            raise SupervisorError("unexpected check-runs response")
        checked[sha] = response["check_runs"]
    return pulls, issues, checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("canopy-review-report.md"))
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("SUPERVISOR_FAIL: GITHUB_TOKEN not supplied", file=sys.stderr)
        return 2
    try:
        pulls, issues, checks = collect(token)
        report = make_report(
            pulls, issues, checks,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        args.out.write_text(report, encoding="utf-8")
    except (SupervisorError, OSError, ValueError) as exc:
        print(f"SUPERVISOR_FAIL: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"SUPERVISOR_PASS: read-only report saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
