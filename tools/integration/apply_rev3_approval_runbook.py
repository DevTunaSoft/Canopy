#!/usr/bin/env python3
"""Rev3 post-approval integration runbook (tools/integration/apply_rev3_approval_runbook.py).

Controlling goal: Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md
SHA-256 1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a.

Modes
  --plan        (default) read-only: re-query live heads/checks/protection, evaluate the
                dependency-ordered chain and trial merges; never mutates a PR or a branch.
  --self-test   offline gate tests; no network, no git writes, no mutations.
  --apply       execute the chain. REQUIRES --distinct-approval <human-login>. Every merge
                is an ordinary GitHub merge API call subject to live branch protection.
                No admin bypass, force-push, self-approval, review creation or PR edit.

All product PRs are pinned to exact heads observed at runbook creation (2026-11-28);
#749 was re-pinned to its remediated head on the same day with a live re-query.
Live review authorization is read from GraphQL `reviewDecision` (the REST pull
object does not carry that field), and each counted review must carry an exact,
non-null `commit_id`. The script refuses to proceed on head/base/scope/check
drift, absent or weakened protection (including disabled
`dismiss_stale_reviews`), unverifiable distinct approval, conflicting trial
merge (including changed sibling blobs in both plan and apply), or post-merge
regression.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

REPO = "DevTunaSoft/Canopy"
INTEGRATION = "integration/canopy-plasma6-20261127"
MAIN = "main"
BASE_SHA = "ec910d7a7275296ecbc8b5e5c459d356205165d1"  # known-good rollback SHA
REV3_SHA256 = "1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a"
REQUIRED_CONTEXTS = ("foundation", "qt-evidence", "fake-gio-launch-fixture")
PROBE_UTC = "2026-11-28T08:10:19Z"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
ROOT = pathlib.Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = ROOT / "scratch" / "rev3_integration_runbook" / "runs"
AUTHOR = "DevTunaSoft"

# number: (head, file_count, sorted-path digest, dependencies, planning title)
# The file-path digest is sha256 of "\\n".join(sorted(PR file paths)) at PROBE_UTC.
PINS: dict[int, dict] = {
    722: dict(head="035fa9c2d00e6f8a0dde7ca70036049010ac436b", files=15,
              paths_sha256="f3033c70396544ded4ca678d7a9552bb68fd2398a42210f6f0ccca6c5616ce9a",
              deps=[], title="master architecture directive"),
    732: dict(head="a14e335a75f35f775bcd669de4e2ba5ab173168c", files=21,
              paths_sha256="872b5c1f1b382aa99103ea8b47d217fe139ae31a602d3c88331f8f594fcc2cc3",
              deps=[736, 737], title="native quick controls with truthful labels"),
    733: dict(head="a0b1c77b94bd0cb3b341a472f68de596ff5f6dce", files=77,
              paths_sha256="842ebeda91665456297d80428c56dadb7c46d327499b58efa941f43f4977b4ce",
              deps=[741], title="native rollback runtime proof (B01 gap closure)"),
    734: dict(head="bd67e7359908b56d53cb68acbb1fb9941b84cc11", files=53,
              paths_sha256="f29b7b4fdc92efdfff7bbd6ee7eea2622aa71758ffb7cdca935de135a4ff1fa1",
              deps=[], title="Kinoite foundation validation (SKIPPED: stale pin/no merge)"),
    735: dict(head="349742749a4ab9dbf2903df876e3d9b70e299986", files=17,
              paths_sha256="be6338bcb0487f994a58a018311234dc7b3c232ed6cdd3bfcbd9a6d6a13ecafc",
              deps=[737], title="native Konsole launch from Terminal dock"),
    736: dict(head="df73dfb6d1272b72e1f57b3b57539373c05dd636", files=10,
              paths_sha256="fabc7db980ca6959269385b36c966a9b8db516a8e3a988d6f7ccb35ce77be766",
              deps=[741], title="native host-event limiter and epoch ceilings"),
    737: dict(head="35c1fe7a0c76cc3dbebe9e3f633b587cbfc377e6", files=45,
              paths_sha256="08a4892bfeab23a30fc7964f7281ae3109983d02faebb4c6445e0d2f4faf9671",
              deps=[741], title="approved dock geometry 32/96/14/7 port (PR729)"),
    738: dict(head="07a5d8c3b750eb7c76d9a69be460384797c4937f", files=23,
              paths_sha256="32acf2a6caec543deefd65791f927fb232b8f8127a189599626eecf0fdfc93f8",
              deps=[], title="native resource baseline (SKIPPED: not accepted)"),
    739: dict(head="cde4b120f427cd1cc682c84037e71169e2f547a3", files=9,
              paths_sha256="ca0fbee95feac441eaa972118c21727dfaf6bbafdfde61e4a25f554abd6cbb02",
              deps=[], title="Shell Pack switching (SKIPPED: incomplete/no wiring)"),
    740: dict(head="f8ba8187bc67b8bf1de49c4e40977f33e17d6e74", files=6,
              paths_sha256="051a9452ea8a5a1baee97926f3a0621468b2a84a84f8747e651f56e421649873",
              deps=[744], title="native AT-SPI role gate fix"),
    741: dict(head="ba1994b835308132ac964520ffcbe032923c177c", files=33,
              paths_sha256="e1f09e234c568be216e276f0494210969b625df4372c998fbeea33924b89107a",
              deps=[722], title="native Plasma 6 development baseline"),
    742: dict(head="83854452db545e30777017906974f69f385bae39", files=74,
              paths_sha256="c4ce9fd00eda665a499945e424fb72b6ebc99cb83d12c630780d11289d18b961",
              deps=[741], title="single TasksModel (SKIPPED: review doc-correction hold)"),
    743: dict(head="2b8bca910d84b19966b29db37dfb3ce7512e810f", files=11,
              paths_sha256="d1f90b03603661edc8ee812ed601161f573e7552ff82e2a69b0eb15a7452ed5a",
              deps=[745], title="native KWin/window/workspace management"),
    744: dict(head="2733f7e09e0e3447fe39eebce6a71171e2ebf476", files=10,
              paths_sha256="b602678ee1bbb4d22e26e42ccfabf8eef7783bc55846d64cd88e6c42649a624f",
              deps=[743], title="native session settings persistence and crash recovery"),
    745: dict(head="80097f8b97b7d5df35b4e53bb9cd835b546aca9f", files=7,
              paths_sha256="1653658480fe5467c605eda30344edd51d1ee28bdd2d3f07ed873b128ec844dd",
              deps=[735], title="native app search over upstream desktop catalog"),
    746: dict(head="050853173419c7224ab8875233f5ef1d7aea622c", files=25,
              paths_sha256="89512bd1a3579e8d65e4b5f1a1d2c96295add701b42d3d9cc37a3a397478b647",
              deps=[744], title="native display response for monitor/HiDPI changes"),
    747: dict(head="ca378da2c2b116db8ce79dc711001add9af59897", files=17,
              paths_sha256="9b9c28c9464574f9efe77729af4bfd2f5530d54dc4ec64d5a130c347bc88ea11",
              deps=[741], title="native notification/tray contracts (single upstream owner)"),
    748: dict(head="9f766d06225f4a7e7cfe9be010a3432a4109ea05", files=20,
              paths_sha256="73a98c383d1fb3a12d7229ae1bb64acb4349589e9c0f81ef23ccc7d82379f501",
              deps=[744], title="native suspend/resume fail-closed verdict contract"),
    749: dict(head="f8cbe123ba2a88edbdc509c5dd8ebe9e20b85260", files=32,
              paths_sha256="aab4da5484cec499d1ffbddeb0fc8b200f6093285e9e26cfa834c3b28894f59b",
              deps=[], title="60m stability soak (SKIPPED: no ready-for-merge promotion)"),
    750: dict(head="0439efa283bad00a92faccc3c62a99cb6a85b605", files=4,
              paths_sha256="b411d30ca22ad91ae6a417a41cc8f3bd0d4cfdc0785fae05e635c5e83633285c",
              deps=[722], title="Rev3 instruction reconciliation"),
}

SKIP = {
    734: "STALE_BODY_HEAD_PIN + NO_MERGE_REQUESTED: body pins 93c4dbc8, live head bd67e735; native runtime NOT_RUN/BLOCKED; body says 'No merge is requested or authorized by this PR'.",
    738: "FAILING_VERDICT: body says BASELINE_CAPTURED_NOT_ACCEPTED with EVIDENCE_GAP (executed-binary hash withdrawn); not an accepted increment.",
    739: "HOLD_INCOMPLETE: INCOMPLETE_600S_CAP (no terminal full-suite verdict) and NO_COMPILED_SWITCHER_WIRING; incomplete runtime wiring.",
    742: "REVIEW_HOLD_DOC_CORRECTION: independent review requires two documentation corrections before promotion; stage_06_verify.log and board_probe.log are ABSENT at the exact head and the '37 tests' claim has no artifact.",
    749: "HOLD_NO_PROMOTION: re-pinned live head f8cbe123ba2a88edbdc509c5dd8ebe9e20b85260 (sampler/report remediated); body still says 'No merge, no self-approval, no ready-for-merge promotion; independent review only'; machine verdict SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT.",
    750: "OVERLAP_HOLD: shares 4 instruction paths (.github/PULL_REQUEST_TEMPLATE.md, AGENTS.md, docs/AGENTS_WORKFORCE.md, docs/ROADMAP.md) with #722; exact-base trial merge conflicts on all four after #722 is promoted. Requires an authorized re-pin onto the post-#722 tip with a fresh independent review and 3/3 checks at the new head. No PR edit is performed by this runbook; the external Rev3 directive SHA remains controlling.",
}

ORDER = [722, 741, 733, 737, 736, 732, 735, 745, 743, 744, 748, 740, 746, 747]

DENY_WORKFLOW = re.compile(r"^\.github/workflows/", re.I)
DENY_HOLD = re.compile(r"(^|/)(AGENTS\.md|MASTER_HANDOFF\.md|NEXT_TASKS\.md)$", re.I)
CONFLICT_MARKER = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\+<<<<<<<|\+>>>>>>>)", re.M)


class Refused(Exception):
    """A gate refused the action. Never swallowed."""


def run(argv, cwd=None, env=None):
    p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def gh_json(endpoint):
    rc, out, err = run(["gh", "api", f"repos/{REPO}/{endpoint}"])
    if rc != 0:
        raise Refused(f"gh api failed for {endpoint}: rc={rc} err={err.strip()[:300]}")
    try:
        return json.loads(out)
    except ValueError as exc:
        raise Refused(f"non-JSON gh api response for {endpoint}: {exc}") from exc


def graphql_review_decision(number):
    """Live GraphQL reviewDecision; REST pulls/<n> does not expose this field.

    Fail closed: an unqueryable or malformed decision is a refusal, never a pass.
    """
    query = ('query($number:Int!){repository(owner:"DevTunaSoft",name:"Canopy")'
             '{pullRequest(number:$number){reviewDecision headRefOid}}}')
    rc, out, err = run(["gh", "api", "graphql", "-f", f"query={query}",
                        "-F", f"number={number}"])
    if rc != 0:
        raise Refused(f"GRAPHQL_REVIEW_DECISION_UNVERIFIABLE #{number}: rc={rc} err={err.strip()[:300]}")
    try:
        data = json.loads(out)
    except ValueError as exc:
        raise Refused(f"GRAPHQL_REVIEW_DECISION_NON_JSON #{number}: {exc}") from exc
    if data.get("errors"):
        raise Refused(f"GRAPHQL_REVIEW_DECISION_ERROR #{number}: {str(data['errors'])[:300]}")
    pr = (((data.get("data") or {}).get("repository") or {}).get("pullRequest"))
    if not isinstance(pr, dict):
        raise Refused(f"GRAPHQL_REVIEW_DECISION_MISSING_PR #{number}")
    return {"review_decision": pr.get("reviewDecision"), "head_ref_oid": pr.get("headRefOid")}


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def check_protection(branch):
    """Live protection must exist and require a distinct human approval + required checks."""
    try:
        prot = gh_json(f"branches/{branch}/protection")
    except Refused as exc:
        raise Refused(f"PROTECTION_UNVERIFIABLE:{branch}: {exc}") from exc
    reviews = prot.get("required_pull_request_reviews") or {}
    admins = prot.get("enforce_admins") or {}
    checks = prot.get("required_status_checks") or {}
    contexts = sorted(c.get("context", "") for c in (checks.get("checks") or [])) or sorted(checks.get("contexts") or [])
    result = {
        "branch": branch,
        "required_approving_review_count": reviews.get("required_approving_review_count"),
        "dismiss_stale_reviews": bool(reviews.get("dismiss_stale_reviews")),
        "enforce_admins": bool(admins.get("enabled")),
        "strict": bool(checks.get("strict")),
        "contexts": contexts,
    }
    problems = []
    if not result["required_approving_review_count"] or result["required_approving_review_count"] < 1:
        problems.append("no required approving review")
    if not result["dismiss_stale_reviews"]:
        problems.append("dismiss_stale_reviews disabled")
    if not result["enforce_admins"]:
        problems.append("enforce_admins disabled")
    if not result["strict"]:
        problems.append("required checks not strict")
    if set(contexts) != set(REQUIRED_CONTEXTS):
        problems.append(f"required check contexts changed: {contexts}")
    result["verdict"] = "PASS" if not problems else "FAIL"
    result["problems"] = problems
    return result


def live_tip():
    rc, out, err = run(["git", "ls-remote", "origin", f"refs/heads/{INTEGRATION}"], cwd=ROOT)
    if rc != 0 or not out.strip():
        raise Refused(f"cannot read live integration tip: {err.strip()[:200]}")
    return out.split()[0]


def normalize_checks(payload, head):
    rows = []
    for c in payload.get("check_runs", []):
        if c.get("head_sha") == head:
            rows.append({"name": c.get("name"),
                         "status": str(c.get("status", "")).lower(),
                         "conclusion": str(c.get("conclusion", "")).lower()})
    verdict = "FAIL"
    if all(any(r["name"] == ctx and r["status"] == "completed" and r["conclusion"] == "success"
               for r in rows) for ctx in REQUIRED_CONTEXTS):
        verdict = "PASS"
    return verdict, rows


def approvals(pr, reviews, approver):
    author = (pr.get("user") or {}).get("login")
    out = []
    for r in reviews:
        user = r.get("user") or {}
        login = user.get("login")
        # A review with commit_id=None is not evidence at any exact head. The
        # old `is None or ...` fallback silently counted stale/unpinned reviews.
        commit_id = r.get("commit_id")
        at_head = bool(commit_id) and commit_id == (pr.get("head") or {}).get("sha")
        if (str(r.get("state", "")).upper() == "APPROVED" and user.get("type") == "User"
                and login and login != author and login == approver and at_head):
            out.append({"login": login, "submitted_at": r.get("submitted_at"),
                        "commit_id": commit_id, "at_exact_head": at_head})
    return out


def verify_skip_reason(number, pr, body):
    """Re-derive every pinned skip from live bytes; a cleared hold still stays skipped."""
    head = (pr.get("head") or {}).get("sha", "")
    if number == 734:
        still = ("93c4dbc8" in body and not head.startswith("93c4dbc8")
                 and "No merge is requested or authorized by this PR" in body)
    elif number == 738:
        still = "BASELINE_CAPTURED_NOT_ACCEPTED" in body
    elif number == 739:
        still = "INCOMPLETE_600S_CAP" in body and "NO_COMPILED_SWITCHER_WIRING" in body
    elif number == 742:
        rc1, _, _ = run(["gh", "api", f"repos/{REPO}/contents/scratch/native_tasks_model/evidence/logs/stage_06_verify.log?ref={head}"])
        rc2, _, _ = run(["gh", "api", f"repos/{REPO}/contents/scratch/native_tasks_model/evidence/logs/board_probe.log?ref={head}"])
        still = (rc1 != 0 and rc2 != 0) or "37 tests" in body
    elif number == 749:
        still = "no ready-for-merge promotion" in body and "SOAK_WARN" in body
    elif number == 750:
        a = gh_json("pulls/722/files?per_page=100")
        b = gh_json("pulls/750/files?per_page=100")
        overlap = {f.get("filename") for f in a} & {f.get("filename") for f in b}
        still = (len(overlap) == 4 and "Do not merge" in body)
    else:
        raise Refused(f"no skip rule for PR {number}")
    return still


def evaluate(number, pin, expected_tip, approver=None):
    """Read-only live evaluation of one pinned PR."""
    pr = gh_json(f"pulls/{number}")
    body = pr.get("body") or ""
    head = (pr.get("head") or {}).get("sha")
    base = pr.get("base") or {}
    files = gh_json(f"pulls/{number}/files?per_page=100")
    paths = sorted(f.get("filename", "") for f in files)
    path_digest = sha256_text("\n".join(paths))
    runs = gh_json(f"commits/{head}/check-runs?per_page=100") if head else {}
    check_verdict, check_rows = normalize_checks(runs, head)
    revs = gh_json(f"pulls/{number}/reviews?per_page=100")
    gql = graphql_review_decision(number) if approver else None
    rec = {
        "number": number, "title": pin["title"], "head_sha": head, "pinned_head": pin["head"],
        "base_ref": base.get("ref"), "base_sha": base.get("sha"), "state": pr.get("state"),
        "merged": pr.get("merged"), "author": (pr.get("user") or {}).get("login"),
        "mergeable": pr.get("mergeable"), "mergeable_state": pr.get("mergeable_state"),
        "review_decision": (gql or {}).get("review_decision"),
        "review_decision_source": "graphql" if gql else "not_queried",
        "file_count": len(paths), "pinned_file_count": pin["files"],
        "paths_sha256": path_digest, "pinned_paths_sha256": pin["paths_sha256"],
        "checks": check_rows, "checks_verdict": check_verdict,
        "approvals": approvals(pr, revs, approver) if approver else [],
    }
    problems = []
    if head != pin["head"]:
        problems.append("HEAD_DRIFT")
    if base.get("ref") != INTEGRATION:
        problems.append("BASE_REF_DRIFT")
    if base.get("sha") != expected_tip:
        problems.append("BASE_TIP_DRIFT")
    if pr.get("state") != "open" or pr.get("merged"):
        problems.append("NOT_OPEN")
    if len(paths) != pin["files"] or path_digest != pin["paths_sha256"]:
        problems.append("SCOPE_DRIFT")
    if check_verdict != "PASS":
        problems.append("CHECKS_NOT_ALL_SUCCESS")
    if pr.get("mergeable") is not True:
        problems.append("NOT_MERGEABLE")
    if pr.get("mergeable_state") in ("dirty", "conflicting", "unknown"):
        problems.append("CONFLICTING_OR_UNKNOWN")
    # AGENTS.md is legitimately owned by #722 (governing architecture) and #750
    # (Rev3 reconciliation) and must be promoted in that order; only *unowned*
    # protected/workflow paths are a gate violation.
    protected_unexpected = [p for p in paths if DENY_WORKFLOW.match(p)
                            or (DENY_HOLD.search(p) and number not in (722, 750))]
    if protected_unexpected:
        problems.append("PROTECTED_PATH_IN_DIFF")
    if approver:
        if not rec["approvals"]:
            problems.append("DISTINCT_APPROVAL_NOT_VERIFIED")
        if str(rec["review_decision"] or "").upper() != "APPROVED":
            problems.append("REVIEW_DECISION_NOT_APPROVED")
        if (gql or {}).get("head_ref_oid") != head:
            problems.append("GRAPHQL_HEAD_DRIFT")
        if pr.get("mergeable_state") == "blocked":
            problems.append("STILL_BLOCKED_BY_PROTECTION")
    rec["problems"] = problems
    rec["eligible"] = not problems
    return rec, paths, body


def fetch_head(number):
    ref = f"refs/rev3-runbook/pr-{number}"
    rc, out, err = run(["git", "fetch", "--no-tags", "origin", f"pull/{number}/head:{ref}"], cwd=ROOT)
    if rc != 0:
        raise Refused(f"cannot fetch PR {number} head: {err.strip()[:300]}")
    rc, out, _ = run(["git", "rev-parse", "--verify", ref], cwd=ROOT)
    return out.strip()


def trial_merge(tip_commit, head_commit, owned_paths, prior_tip=None):
    """Sequential exact-SHA trial merge; no branch, no PR, no remote mutation."""
    # This checkout is shallow; all pinned PRs branch from BASE_SHA, so pin the merge
    # base explicitly instead of relying on ancestry discovery across a shallow boundary.
    rc, out, err = run(["git", "merge-tree", "--write-tree", "--merge-base", BASE_SHA,
                        tip_commit, head_commit], cwd=ROOT)
    if rc != 0:
        raise Refused(f"TRIAL_MERGE_CONFLICT rc={rc} err={err.strip()[:400]}")
    if CONFLICT_MARKER.search(out):
        raise Refused("TRIAL_MERGE_CONFLICT_MARKERS")
    tree = out.strip().splitlines()[0]
    if not HEX40.match(tree):
        raise Refused(f"TRIAL_MERGE_BAD_TREE {tree[:80]}")
    rc, delta, err = run(["git", "diff", "--name-status", tip_commit, tree], cwd=ROOT)
    if rc != 0:
        raise Refused(f"trial delta failed: {err.strip()[:200]}")
    net_paths = []
    for line in delta.splitlines():
        parts = line.split("\t")
        if len(parts) > 1:
            net_paths.append(parts[-1])
    unowned = sorted(set(net_paths) - set(owned_paths))
    if unowned:
        raise Refused(f"TRIAL_MERGE_UNOWNED_PATHS {unowned[:8]}")
    if DENY_WORKFLOW.search("".join(p + "\n" for p in net_paths)):
        raise Refused("TRIAL_MERGE_WORKFLOW_PATH")
    # Every sibling path already at the tip must be byte-identical in the trial tree.
    sibling_changed = []
    if prior_tip:
        rc, changed, _ = run(["git", "diff", "--name-only", prior_tip, tip_commit], cwd=ROOT)
        for p in (x for x in changed.splitlines() if x and x not in owned_paths):
            rc1, a, _ = run(["git", "rev-parse", f"{tip_commit}:{p}"], cwd=ROOT)
            rc2, b, _ = run(["git", "rev-parse", f"{tree}:{p}"], cwd=ROOT)
            if rc1 == 0 and (rc2 != 0 or a.strip() != b.strip()):
                sibling_changed.append(p)
    if sibling_changed:
        raise Refused(f"TRIAL_MERGE_SIBLING_BLOB_CHANGED {sibling_changed[:8]}")
    env = dict(os.environ, GIT_AUTHOR_NAME="rev3-runbook", GIT_AUTHOR_EMAIL="runbook@local",
               GIT_COMMITTER_NAME="rev3-runbook", GIT_COMMITTER_EMAIL="runbook@local")
    rc, commit, err = run(["git", "commit-tree", tree, "-p", tip_commit, "-p", head_commit,
                           "-m", "LOCAL TRIAL ONLY - rev3 runbook"], cwd=ROOT, env=env)
    if rc != 0 or not HEX40.match(commit.strip()):
        raise Refused(f"TRIAL_COMMIT_FAILED {err.strip()[:200]}")
    return {"tree": tree, "trial_commit": commit.strip(), "net_paths": sorted(net_paths),
            "unowned_paths": [], "conflict": False}


def write_evidence(stamp, payload):
    out = EVIDENCE_ROOT / stamp
    out.mkdir(parents=True, exist_ok=True)
    target = out / "run.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    sums = []
    for p in sorted(out.iterdir()):
        if p.name == "SHA256SUMS.txt" or p == target:
            continue
        sums.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n")
    sums.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  run.json\n")
    (out / "SHA256SUMS.txt").write_text("".join(sums), encoding="ascii", newline="\n")
    return str(target)


def merge_exact(number, head):
    """Ordinary GitHub merge API. No --admin, no force-push, no review creation."""
    rc, out, err = run(["gh", "api", "-X", "PUT", f"repos/{REPO}/pulls/{number}/merge",
                        "-f", "merge_method=merge", "-f", f"sha={head}"])
    if rc != 0:
        raise Refused(f"MERGE_API_FAILED #{number}: {err.strip()[:300]}")
    try:
        data = json.loads(out)
    except ValueError as exc:
        raise Refused(f"MERGE_RESPONSE_NOT_JSON #{number}: {exc}") from exc
    if not data.get("merged"):
        raise Refused(f"MERGE_NOT_RECORDED #{number}: {str(data)[:200]}")
    return {"number": number, "sha": data.get("sha"), "message": data.get("message")}


def poll_checks(tip, attempts, interval):
    history = []
    for i in range(attempts):
        rc, out, err = run(["gh", "api", f"repos/{REPO}/commits/{tip}/check-runs?per_page=100"])
        if rc == 0:
            verdict, rows = normalize_checks(json.loads(out), tip)
            history.append({"attempt": i + 1, "verdict": verdict, "checks": rows, "at": utcnow()})
            if verdict == "PASS":
                return True, history
        else:
            history.append({"attempt": i + 1, "verdict": "QUERY_FAILED", "error": err.strip()[:200], "at": utcnow()})
        if i + 1 < attempts:
            import time
            time.sleep(interval)
    return False, history


def post_merge(tip, number, attempts, interval, full_suite):
    ok, polls = poll_checks(tip, attempts, interval)
    result = {"merge_commit": tip, "pr": number, "checks_pass": ok, "polls": polls,
              "foundation": "NOT_RUN", "full_suite": "NOT_RUN"}
    if not ok:
        return result
    with tempfile.TemporaryDirectory(prefix="rev3-postmerge-") as tmp:
        rc, out, err = run(["git", "init", "-q"], cwd=tmp)
        rc, out, err = run(["git", "fetch", "--no-tags", "--depth=1", "origin", tip], cwd=tmp)
        if rc != 0:
            result["checkout"] = f"FETCH_FAILED {err.strip()[:200]}"
            return result
        rc, out, err = run(["git", "checkout", "--detach", "-q", "FETCH_HEAD"], cwd=tmp)
        if rc != 0:
            result["checkout"] = f"CHECKOUT_FAILED {err.strip()[:200]}"
            return result
        rc, out, err = run([sys.executable, "tools/check_foundation.py"], cwd=tmp)
        result["foundation"] = "PASS" if rc == 0 else "FAIL"
        result["foundation_log"] = (out + "\n" + err)[-4000:]
        if full_suite and rc == 0:
            rc, out, err = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=tmp)
            text = (out + "\n" + err).replace("\r\n", "\n")
            terminal = bool(re.search(r"^Ran \d+ tests? in ", text, re.M)) and "OK" in text and "FAILED" not in text
            result["full_suite"] = "PASS" if rc == 0 and terminal else "FAIL"
            result["full_suite_summary"] = text[-4000:]
        elif not full_suite:
            result["full_suite"] = "NOT_RUN"
    return result


def rollback_plan(merges):
    return {
        "known_good_sha": BASE_SHA,
        "branch": INTEGRATION,
        "rule": "Never rewrite history; restore by reverting merged commits in reverse order through new independently reviewed PRs with the same distinct-human approval and protection gates.",
        "verify_known_good": f"git ls-remote origin refs/heads/{INTEGRATION}  # expect {BASE_SHA}",
        "reverse_reverts": [f"git revert -m 1 {m['sha']}" for m in reversed(merges)],
        "post_revert": "Re-run foundation + full suite at the restored tip; pause dependent integrations until green.",
        "forbidden": ["git push --force", "git reset --hard on integration", "admin bypass", "self-approval"],
    }


def self_test():
    rec = {"name": "foundation", "status": "COMPLETED", "conclusion": "SUCCESS",
           "head_sha": "a" * 40}
    verdict, rows = normalize_checks({"check_runs": [rec] + [
        {"name": n, "status": "COMPLETED", "conclusion": "SUCCESS", "head_sha": "a" * 40}
        for n in REQUIRED_CONTEXTS[1:]]}, "a" * 40)
    assert verdict == "PASS", rows
    bad = dict(rec, conclusion="FAILURE")
    assert normalize_checks({"check_runs": [bad]}, "a" * 40)[0] == "FAIL"
    assert normalize_checks({"check_runs": [dict(rec, head_sha="b" * 40)]}, "a" * 40)[0] == "FAIL"
    pr = {"user": {"login": AUTHOR}, "head": {"sha": "a" * 40}}
    good = {"user": {"login": "human-reviewer", "type": "User"}, "state": "APPROVED", "commit_id": "a" * 40}
    assert approvals(pr, [good], "human-reviewer")
    assert not approvals(pr, [good], AUTHOR), "author cannot self-approve"
    bot = dict(good, user={"login": "action-bot", "type": "Bot"})
    assert not approvals(pr, [bot], "action-bot"), "bot cannot approve"
    stale = dict(good, commit_id="c" * 40)
    assert not approvals(pr, [stale], "human-reviewer"), "stale-head review must not count"
    unpinned = dict(good, commit_id=None)
    assert not approvals(pr, [unpinned], "human-reviewer"), "commit_id=None must not count"
    for n, marker in [(734, "No merge is requested or authorized by this PR"),
                      (738, "BASELINE_CAPTURED_NOT_ACCEPTED"),
                      (749, "no ready-for-merge promotion")]:
        assert marker, n
    assert len(ORDER) == 14 and len(SKIP) == 6 and len(PINS) == 20
    assert set(ORDER).isdisjoint(SKIP)
    assert set(ORDER) | set(SKIP) == set(PINS)
    for n in ORDER:
        for dep in PINS[n]["deps"]:
            assert dep in ORDER and ORDER.index(dep) < ORDER.index(n), f"dependency order broken at #{n}"
    assert HEX40.match(BASE_SHA) and HEX40.match(REV3_SHA256) is None
    assert len(REV3_SHA256) == 64
    pin749 = PINS[749]
    assert pin749["head"] == "f8cbe123ba2a88edbdc509c5dd8ebe9e20b85260"
    assert pin749["files"] == 32
    assert pin749["paths_sha256"] == "aab4da5484cec499d1ffbddeb0fc8b200f6093285e9e26cfa834c3b28894f59b"

    # Offline protection gate: dismiss_stale_reviews must be explicitly true.
    prot = {"required_pull_request_reviews": {
                "required_approving_review_count": 1, "dismiss_stale_reviews": True},
            "enforce_admins": {"enabled": True},
            "required_status_checks": {"strict": True,
                                       "checks": [{"context": c} for c in REQUIRED_CONTEXTS]}}
    saved_gh, saved_gql = globals()["gh_json"], globals()["graphql_review_decision"]
    try:
        globals()["gh_json"] = lambda endpoint: prot
        assert check_protection(INTEGRATION)["verdict"] == "PASS"
        weak = json.loads(json.dumps(prot))
        weak["required_pull_request_reviews"]["dismiss_stale_reviews"] = False
        globals()["gh_json"] = lambda endpoint: weak
        assert "dismiss_stale_reviews disabled" in check_protection(INTEGRATION)["problems"]

        # Offline end-to-end decision gate: REST review_decision is ignored;
        # GraphQL reviewDecision decides, and a null decision refuses.
        live_pr = {"user": {"login": AUTHOR}, "head": {"sha": "a" * 40},
                   "base": {"ref": INTEGRATION, "sha": "a" * 40},
                   "state": "open", "merged": False, "mergeable": True,
                   "mergeable_state": "clean", "review_decision": "APPROVED"}
        file_row = {"filename": "docs/self_test.txt"}
        check_payload = {"check_runs": [dict(rec, name=c) for c in REQUIRED_CONTEXTS]}
        globals()["gh_json"] = lambda endpoint: (
            live_pr if endpoint.endswith("/pulls/722") or endpoint == "pulls/722" else
            [file_row] if endpoint.endswith("/files?per_page=100") else
            check_payload if "check-runs" in endpoint else [good])
        globals()["graphql_review_decision"] = lambda n: {
            "review_decision": "APPROVED", "head_ref_oid": "a" * 40}
        pin = dict(PINS[722], head="a" * 40, files=1,
                   paths_sha256=sha256_text("docs/self_test.txt"))
        approved, _, _ = evaluate(722, pin, "a" * 40, "human-reviewer")
        assert approved["eligible"], approved["problems"]
        assert approved["review_decision_source"] == "graphql"
        globals()["graphql_review_decision"] = lambda n: {
            "review_decision": "REVIEW_REQUIRED", "head_ref_oid": "a" * 40}
        refused, _, _ = evaluate(722, pin, "a" * 40, "human-reviewer")
        assert "REVIEW_DECISION_NOT_APPROVED" in refused["problems"], refused["problems"]
        globals()["graphql_review_decision"] = lambda n: {
            "review_decision": "APPROVED", "head_ref_oid": "b" * 40}
        drift, _, _ = evaluate(722, pin, "a" * 40, "human-reviewer")
        assert "GRAPHQL_HEAD_DRIFT" in drift["problems"], drift["problems"]
    finally:
        globals()["gh_json"], globals()["graphql_review_decision"] = saved_gh, saved_gql

    apply_src = inspect.getsource(apply_runbook)
    assert "prior_tip" in apply_src and "trial_merge(trial_tip" in apply_src, "apply sibling gate missing"
    assert "verify_approval_and_protection" in apply_src, "apply pre-merge gate missing"
    main_src = inspect.getsource(main)
    assert 'ap.add_argument("--plan", action="store_true"' in main_src
    assert 'ap.add_argument("--apply", action="store_true"' in main_src
    assert "DISTINCT_APPROVAL_FLAG_REQUIRED" in inspect.getsource(apply_runbook)
    print("SELF_TEST_PASS gates=checks+approval+graphql-decision+commit-id+dismiss-stale+order+skip-disjointness+pin-shape+apply-sibling")


def plan(approver=None):
    tip = live_tip()
    out = {"generated_utc": utcnow(), "probe_utc": PROBE_UTC, "rev3_sha256": REV3_SHA256,
           "known_good_rollback_sha": BASE_SHA, "base_pin": BASE_SHA, "live_tip": tip,
           "integration": INTEGRATION, "main": MAIN, "protection": {}, "skipped": {},
           "candidates": [], "sequence": [], "trial": [], "verdict": ""}
    for branch in (INTEGRATION, MAIN):
        out["protection"][branch] = check_protection(branch)
    if any(v["verdict"] != "PASS" for v in out["protection"].values()):
        raise Refused("PROTECTION_NOT_VERIFIED; refusing to plan an executable merge chain")
    for n in sorted(SKIP):
        pr = gh_json(f"pulls/{n}")
        still = verify_skip_reason(n, pr, pr.get("body") or "")
        out["skipped"][str(n)] = {"reason": SKIP[n], "hold_rederived_live": still,
                                   "action": "SKIP; re-baseline only after an authorized new review"}
    trial_tip, prior_tip = tip, None
    for n in ORDER:
        pin = PINS[n]
        rec, paths, _ = evaluate(n, pin, tip, approver)
        out["candidates"].append(rec)
        if not rec["eligible"]:
            out["sequence"].append({"pr": n, "status": "SKIPPED", "problems": rec["problems"]})
            continue
        head = fetch_head(n)
        if head != pin["head"]:
            raise Refused(f"fetched head drift for PR {n}")
        try:
            tm = trial_merge(trial_tip, head, set(paths), prior_tip)
        except Refused as exc:
            raise Refused(f"PR {n} trial merge against {trial_tip[:12]} failed: {exc}") from exc
        out["trial"].append({"pr": n, "against": trial_tip, **tm})
        out["sequence"].append({"pr": n, "status": "TRIAL_CLEAN", "head": head, "trial_tree": tm["tree"]})
        prior_tip, trial_tip = trial_tip, tm["trial_commit"]
    out["verdict"] = ("PLAN_ONLY_DISTINCT_APPROVAL_PENDING" if not approver else
                      "APPROVAL_VERIFIED_READY_TO_APPLY")
    return out


def verify_approval_and_protection(number, head, approver):
    """Last-moment, read-only re-check immediately before an ordinary merge.

    Re-query the live review state (GraphQL decision + exact non-null commit_id)
    and both branch protections. No gate may be cached from planning time.
    """
    problems = []
    pr = gh_json(f"pulls/{number}")
    if (pr.get("head") or {}).get("sha") != head:
        problems.append("HEAD_DRIFT_BEFORE_MERGE")
    revs = gh_json(f"pulls/{number}/reviews?per_page=100")
    if not approvals(pr, revs, approver):
        problems.append("APPROVAL_WITHDRAWN_OR_STALE")
    gql = graphql_review_decision(number)
    if str(gql.get("review_decision") or "").upper() != "APPROVED":
        problems.append("REVIEW_DECISION_NOT_APPROVED")
    if gql.get("head_ref_oid") != head:
        problems.append("GRAPHQL_HEAD_DRIFT")
    for branch in (INTEGRATION, MAIN):
        p = check_protection(branch)
        if p["verdict"] != "PASS":
            problems.append(f"PROTECTION_CHANGED:{branch}:{','.join(p['problems'])}")
        if not p["dismiss_stale_reviews"]:
            problems.append(f"DISMISS_STALE_REVIEWS_DISABLED:{branch}")
    return {"verdict": "PASS" if not problems else "FAIL", "problems": problems,
            "review_decision": gql.get("review_decision"),
            "review_decision_source": "graphql"}


def apply_runbook(approver, attempts, interval, full_suite):
    if not approver:
        raise Refused("DISTINCT_APPROVAL_FLAG_REQUIRED: --apply needs --distinct-approval <human-login>")
    if approver.lower() == AUTHOR.lower() or approver.endswith("[bot]"):
        raise Refused("APPROVER_NOT_DISTINCT_HUMAN")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state = {"mode": "apply", "started_utc": utcnow(), "rev3_sha256": REV3_SHA256,
             "known_good_rollback_sha": BASE_SHA, "distinct_approval": approver,
             "full_suite": full_suite, "merges": [], "post_merge": [], "skipped": SKIP,
             "verdict": "IN_PROGRESS"}
    evidence_file = write_evidence(stamp, state)
    for branch in (INTEGRATION, MAIN):
        p = check_protection(branch)
        state.setdefault("protection", {})[branch] = p
        if p["verdict"] != "PASS":
            state["verdict"] = "REFUSED_PROTECTION"
            write_evidence(stamp, state)
            raise Refused("PROTECTION_NOT_VERIFIED")
    tip = live_tip()
    if tip != BASE_SHA:
        state["verdict"] = "REFUSED_BASE_DRIFT"
        write_evidence(stamp, state)
        raise Refused(f"LIVE_TIP_DRIFT expected {BASE_SHA} got {tip}")
    # Mirror the plan's sequential trial chain. The sibling-blob comparison uses
    # the previous trial tip (prior_tip); dropping it in --apply would let a
    # merge silently overwrite a sibling's already-integrated bytes.
    prior_tip, trial_tip = None, tip
    for n in ORDER:
        rec, paths, _ = evaluate(n, PINS[n], tip, approver)
        if not rec["eligible"]:
            state["verdict"] = f"STOPPED_PR_{n}_GATES"
            state.setdefault("gate_failures", {})[str(n)] = rec["problems"]
            write_evidence(stamp, state)
            raise Refused(f"PR {n} gate failure: {rec['problems']}")
        head = fetch_head(n)
        if head != PINS[n]["head"]:
            state["verdict"] = f"STOPPED_PR_{n}_HEAD_DRIFT"
            write_evidence(stamp, state)
            raise Refused(f"PR {n} fetched head drift")
        try:
            tm = trial_merge(trial_tip, head, set(paths), prior_tip)
        except Refused as exc:
            state["verdict"] = f"STOPPED_PR_{n}_TRIAL_MERGE"
            write_evidence(stamp, state)
            raise Refused(f"PR {n} trial merge against {trial_tip[:12]} failed: {exc}") from exc
        state.setdefault("trials", {})[str(n)] = {"pr": n, "against": trial_tip,
                                                   "prior_tip": prior_tip, **tm}
        write_evidence(stamp, state)
        prior_tip, trial_tip = trial_tip, tm["trial_commit"]
        # Re-check live tip immediately before the merge (serialized integration).
        now = live_tip()
        if now != tip:
            state["verdict"] = f"STOPPED_PR_{n}_TIP_ADVANCED"
            write_evidence(stamp, state)
            raise Refused(f"live tip advanced from {tip} to {now}")
        gates = verify_approval_and_protection(n, head, approver)
        state.setdefault("pre_merge_gates", {})[str(n)] = gates
        write_evidence(stamp, state)
        if gates["verdict"] != "PASS":
            state["verdict"] = f"STOPPED_PR_{n}_PRE_MERGE_GATES"
            write_evidence(stamp, state)
            raise Refused(f"PR {n} pre-merge gate failure: {gates['problems']}")
        merged = merge_exact(n, head)
        state["merges"].append(merged)
        write_evidence(stamp, state)
        post = post_merge(merged["sha"], n, attempts, interval, full_suite)
        state["post_merge"].append(post)
        write_evidence(stamp, state)
        if not post["checks_pass"] or post["foundation"] != "PASS" or post["full_suite"] == "FAIL":
            state["verdict"] = f"STOPPED_PR_{n}_POST_MERGE_REGRESSION"
            state["rollback"] = rollback_plan(state["merges"])
            write_evidence(stamp, state)
            raise Refused(f"post-merge regression at PR {n}; rollback plan written")
        if post["full_suite"] == "NOT_RUN":
            state["verdict"] = f"STOPPED_PR_{n}_FULL_SUITE_NOT_RUN"
            write_evidence(stamp, state)
            raise Refused("full suite not run; dependent integrations paused")
        tip = merged["sha"]
    state["verdict"] = "APPLIED_ALL_POST_APPROVAL_MERGES"
    state["final_tip"] = tip
    state["rollback"] = rollback_plan(state["merges"])
    state["evidence_file"] = evidence_file
    write_evidence(stamp, state)
    return state


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true", help="read-only live re-query + trial merges (default)")
    ap.add_argument("--self-test", action="store_true", help="offline gate tests; no network and no mutations")
    ap.add_argument("--apply", action="store_true", help="execute after every gate passes (mutating)")
    ap.add_argument("--distinct-approval", metavar="LOGIN", default=None,
                    help="EXPLICIT flag: login of the real distinct human approver; required by --apply")
    ap.add_argument("--poll-attempts", type=int, default=20)
    ap.add_argument("--poll-interval", type=int, default=30)
    ap.add_argument("--foundation-only", action="store_true",
                    help="record full suite NOT_RUN and stop after first merge (conservative)")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.apply and args.plan:
        print("refuse: --apply and --plan are mutually exclusive", file=sys.stderr)
        return 2
    try:
        if args.apply:
            result = apply_runbook(args.distinct_approval, args.poll_attempts,
                                   args.poll_interval, not args.foundation_only)
        else:
            result = plan(args.distinct_approval)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
