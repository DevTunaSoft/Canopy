# Rev3 post-approval integration runbook (2026-11-28)

## Status and boundary

- Controlling goal: `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md` SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a` (short `1fba4b1e`).
- Base / known-good rollback SHA: `ec910d7a7275296ecbc8b5e5c459d356205165d1` (`integration/canopy-plasma6-20261127` live tip at drafting).
- Runbook branch: `integration/rev3-approval-runbook-20261128`, created from `ec910d7a`. It owns only `tools/integration/apply_rev3_approval_runbook.py`, `docs/REV3_INTEGRATION_RUNBOOK.md` and `scratch/rev3_integration_runbook/**`.
- **This runbook did not merge, approve, edit, promote or comment on any PR.** It did not change any protection setting, global config, visual asset, named hold (#151/#278/#279) or security/release gate. Its only remote mutation is pushing its own runbook branch. (Creating this remediation worktree is a local checkout change, not a remote or PR mutation.)
- At drafting, all 14 ordered candidates were mergeable with 3/3 terminal `success` checks at their exact heads and no approving review; green CI is evidence, not authorization. Six further PRs are held for independent reasons (below), not merely for lack of approval.

## Live evidence captured at drafting (UTC 2026-11-28T08:10:19Z)

- Integration and `main` protection: `required_approving_review_count=1`, `dismiss_stale_reviews=true`, `enforce_admins.enabled=true`, `strict=true`, required contexts `foundation`, `qt-evidence`, `fake-gio-launch-fixture`.
- Every PR base ref/sha = `integration/canopy-plasma6-20261127` / `ec910d7a…`; all 20 heads pinned in the script; all 20 file-path sets pinned by count and SHA-256.
- Raw curated probes: `scratch/rev3_integration_runbook/evidence/live_state_20261128.json`, `protection_20261128.json`, `trial_merge_20261128.json`, `decisions_20261128.json`, `pr750_conflict_20261128.txt`, plus the remediation re-pin probe `repin_749_20261128.json`; directory verified with `SHA256SUMS.txt`.

## Execution gate (mandatory)

```bash
cd C:/Users/X1/Projects/Canopy
python tools/integration/apply_rev3_approval_runbook.py --self-test
python tools/integration/apply_rev3_approval_runbook.py --plan
# ONLY after a real distinct human APPROVED review exists at the exact head:
python tools/integration/apply_rev3_approval_runbook.py --apply --distinct-approval <human-login>
```

- `--plan` (default) is read-only with respect to GitHub and tracked files: it re-queries live state and runs sequential local trial merges. It **does** write local git objects and fetch refs under `refs/rev3-runbook/*`; it never pushes, merges, approves, comments, edits tracked files or changes protection.
- `--apply` **refuses without `--distinct-approval <login>`** and refuses when the login is the PR author (`DevTunaSoft`) or a bot, when no `APPROVED` review from that login exists with an exact non-null `commit_id` at the pinned head, when the live GraphQL `reviewDecision` is not `APPROVED` (the REST pull object has no such field), or when `mergeable_state` is still `blocked`.
- Protection is re-queried at plan time and again immediately before each merge. A missing/changed protection API, weaker review requirement, `dismiss_stale_reviews` disabled, disabled `enforce_admins`, non-strict checks or changed required contexts refuses the run.
- The only merge call is the ordinary GitHub merge API (`PUT /pulls/<n>/merge` with `merge_method=merge` and the exact head `sha`). There is **no** admin endpoint, `--admin`, force-push, reset, review creation, self-approval or PR edit anywhere in the script.
- Head/base/scope/check drift, non-mergeable or conflicting state, unexpected protected/workflow paths, a dirty trial merge, a changed sibling blob in the sequential trial chain (`prior_tip` comparison in **both** plan and apply), a live tip that advanced before the merge, a failed last-moment approval/protection re-check, or a post-merge regression stop the chain and write refusal evidence to `scratch/rev3_integration_runbook/runs/<UTC>/run.json` with a `SHA256SUMS.txt` sidecar.

## Exact dependency-ordered merge sequence (14 merges)

| # | PR | Exact head | Depends on | Reason |
|---|----|------------|------------|--------|
| 1 | #722 | `035fa9c2d00e6f8a0dde7ca70036049010ac436b` | — | Governing architecture (Rev3 A2.1); owns four instruction files |
| 2 | #741 | `ba1994b835308132ac964520ffcbe032923c177c` | #722 | Installable native Plasma 6 development baseline (A2.2) |
| 3 | #733 | `a0b1c77b94bd0cb3b341a472f68de596ff5f6dce` | #741 | Real rollback proof closes B01 gaps against the #741 install baseline |
| 4 | #737 | `35c1fe7a0c76cc3dbebe9e3f633b587cbfc377e6` | #741 | Approved dock geometry 32/96/14/7 port with synced test pins |
| 5 | #736 | `df73dfb6d1272b72e1f57b3b57539373c05dd636` | #741 | Host-event limiter/epoch ceilings for reliable native events |
| 6 | #732 | `a14e335a75f35f775bcd669de4e2ba5ab173168c` | #736, #737 | Bounded native quick controls with truthful PASS/NOT_RUN labels |
| 7 | #735 | `349742749a4ab9dbf2903df876e3d9b70e299986` | #737 | Native Konsole launch from the restored Terminal dock tile |
| 8 | #745 | `80097f8b97b7d5df35b4e53bb9cd835b546aca9f` | #735 | Native launcher search over the same upstream desktop catalog |
| 9 | #743 | `2b8bca910d84b19966b29db37dfb3ce7512e810f` | #745 | Bounded KWin/window/workspace decision boundary |
| 10 | #744 | `2733f7e09e0e3447fe39eebce6a71171e2ebf476` | #743 | Session settings persistence and crash recovery |
| 11 | #748 | `9f766d06225f4a7e7cfe9be010a3432a4109ea05` | #744 | Fail-closed suspend/resume verdicts over recovered session state |
| 12 | #740 | `f8ba8187bc67b8bf1de49c4e40977f33e17d6e74` | #744 | Native AT-SPI role vocabulary and scoped verification |
| 13 | #746 | `050853173419c7224ab8875233f5ef1d7aea622c` | #744 | Bounded display response for monitor add/remove and HiDPI |
| 14 | #747 | `ca378da2c2b116db8ce79dc711001add9af59897` | #741 | Notifications/tray reusing the single upstream Plasma owner |

The dependency list is topological and asserted by `--self-test`. `#750` depends on `#722` by file overlap but is held (below); `#741` therefore follows `#722` directly.

## Skipped PRs (re-derived live at plan time; holds remain authoritative)

| PR | Reason |
|----|--------|
| #734 | Body still pins stale head `93c4dbc8` while live head is `bd67e735…`; native runtime `NOT_RUN/BLOCKED`; body states "No merge is requested or authorized by this PR". |
| #738 | `BASELINE_CAPTURED_NOT_ACCEPTED`; executed-binary hash withdrawn as `EVIDENCE_GAP`; no accepted increment. |
| #739 | `INCOMPLETE_600S_CAP` (no terminal full-suite verdict) and `NO_COMPILED_SWITCHER_WIRING`. |
| #742 | Independent review requires two documentation corrections before promotion; `stage_06_verify.log` and `board_probe.log` are ABSENT at the exact head and the "37 tests" claim has no artifact. |
| #749 | Re-pinned to live head `f8cbe123ba2a88edbdc509c5dd8ebe9e20b85260` (sampler/report remediated); body still says "no merge, no self-approval, no ready-for-merge promotion; independent review only"; machine verdict `SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT`. |
| #750 | `OVERLAP_HOLD`: shares `.github/PULL_REQUEST_TEMPLATE.md`, `AGENTS.md`, `docs/AGENTS_WORKFORCE.md`, `docs/ROADMAP.md` with #722. Trial merge onto the post-#722 trial tree conflicts in all four files (`pr750_conflict_20261128.txt`). Requires an authorized re-pin onto the post-#722 tip, a fresh independent review and 3/3 checks at the new head. The external Rev3 directive SHA remains controlling in the meantime. No PR edit is performed by this runbook. |

A hold that appears cleared live is still skipped: re-baselining needs a new authorized review, not an automatic promotion.

## Trial merge result validation

For each candidate, after live checks pass:

```bash
git fetch --no-tags origin pull/<n>/head:refs/rev3-runbook/pr-<n>
git merge-tree --write-tree --merge-base ec910d7a7275296ecbc8b5e5c459d356205165d1 \
    <evolving-trial-tip> <exact-pr-head>
git diff --name-status <trial-tip> <trial-tree>
```

The script refuses on non-zero rc, conflict markers, any net path outside the PR's pinned file set, workflow/unowned protected paths, or a sibling path whose blob changed between the prior and current trial tip. The `prior_tip` sibling comparison runs in `--plan` **and** `--apply`; `apply` uses the evolving trial commit from the preceding PR, not just the live tip. `--merge-base` is pinned to `ec910d7a` because this checkout is shallow; every pinned PR branches from that base. The trial commit is a local `commit-tree` object only — no ref, branch, PR or remote is changed by the trial itself (the separate `fetch` step does create local `refs/rev3-runbook/*`).

Observed at drafting: **14/14 trial merges clean**; #750 conflicts on the four shared instruction files and is held. The post-#722 **trial commit** was `6473bac4afd674429e087bd2fff6c001e7f45a5d`; its **tree** was `5a38dc10cc9293fa37471329d6ba2d06132ab83d`. A commit SHA and a tree SHA are different objects and are labelled separately in evidence (`trial_commit` vs `tree`/`trial_tree`).

## Post-merge checks and regression stop

After each ordinary merge the script:

1. Re-queries the merge commit and polls `foundation`, `qt-evidence`, `fake-gio-launch-fixture` at the new integration tip to terminal success (bounded polls, configurable `--poll-attempts`/`--poll-interval`).
2. Creates a fresh temporary checkout pinned to the exact merge SHA (`git init`, depth-1 fetch, detached checkout) and runs `python tools/check_foundation.py`.
3. Runs `python -m unittest discover -s tests`, parsing the terminal `Ran N tests` summary from stdout **and** stderr; `FAILED` or a non-terminal summary is a regression. `--foundation-only` deliberately records `NOT_RUN`, stops the chain and does not authorize the next merge.
4. Writes per-step JSON evidence (merge SHA, check polls, logs, verdict and the pre-merge gate re-check) and a directory `SHA256SUMS.txt` under `scratch/rev3_integration_runbook/runs/<UTC>/`. First-parent continuity is enforced by merging the exact pinned head onto the single live tip; it is **not** recorded as a separate measured field.

Any regression stops dependent integrations immediately; unaffected independent work is not touched by this script.

## Known-good rollback

- Known-good SHA: `ec910d7a7275296ecbc8b5e5c459d356205165d1`.
- Verify: `git ls-remote origin refs/heads/integration/canopy-plasma6-20261127` (must equal the known-good SHA before the first merge).
- On regression: stop, capture evidence, then restore by `git revert -m 1 <merge_sha>` for merged commits **in reverse order**, each through a new independently reviewed PR with the same distinct-human approval and protection gates; rerun foundation + full suite at the restored tip.
- Forbidden: force-push, `git reset --hard` on the integration branch, admin bypass, self-approval, history rewriting. The script only emits the rollback plan; it never executes a revert.

## Verification performed for this runbook and its remediation

- `python tools/integration/apply_rev3_approval_runbook.py --self-test` → `SELF_TEST_PASS gates=checks+approval+graphql-decision+commit-id+dismiss-stale+order+skip-disjointness+pin-shape+apply-sibling`: check normalization, distinct-human approval incl. author/bot/stale-head/`commit_id=None` negatives, a mocked GraphQL `APPROVED` decision that passes and `REVIEW_REQUIRED`/head-drift decisions that refuse, protection with `dismiss_stale_reviews=false` that refuses, topological order, skip/order disjointness, pin shape and presence of the apply sibling/pre-merge gates.
- `python tools/integration/apply_rev3_approval_runbook.py --plan` → `PLAN_ONLY_DISTINCT_APPROVAL_PENDING`; 14 `TRIAL_CLEAN`; 6 skip holds re-derived live; both branch protections `PASS` with `dismiss_stale_reviews=true`. No PR or branch was mutated.
- `python tools/integration/apply_rev3_approval_runbook.py --apply` (no flag) → `REFUSED: DISTINCT_APPROVAL_FLAG_REQUIRED`, rc=3, no merge attempted.
- `python tools/integration/apply_rev3_approval_runbook.py --apply --distinct-approval fake-human` → refused at PR #722 with `DISTINCT_APPROVAL_NOT_VERIFIED`, `REVIEW_DECISION_NOT_APPROVED`, `STILL_BLOCKED_BY_PROTECTION`, rc=3; evidence `scratch/rev3_integration_runbook/runs/20261128T094104Z/run.json`; no merge attempted. The decision check now reads the live GraphQL field instead of the absent REST field, so a genuine distinct approval can evaluate.
- Live GraphQL re-query: `reviewDecision=REVIEW_REQUIRED` for #722 and #749; #722 `headRefOid` matched its REST head. No review was created by this runbook.
- #749 re-pin was verified live at `f8cbe123ba2a88edbdc509c5dd8ebe9e20b85260`: 32 files, paths SHA-256 `aab4da5484cec499d1ffbddeb0fc8b200f6093285e9e26cfa834c3b28894f59b`, 3/3 terminal `success` checks at that head, body still withholding promotion. A later live push moved #749 to `bff56000…`; that is `HEAD_DRIFT` under the script and #749 remains skipped — no promotion was attempted.

## Remediation of review holds G1–G4 (branch head 166546a)

- G1 — replaced the REST `review_decision` gate (always `None` on REST pull objects) with a live GraphQL `reviewDecision` query, cross-checked against `headRefOid`; fail closed on query errors, null decisions or head drift.
- G2 — re-pinned #749 to `f8cbe123…` with a live-derived file count/path digest, and refreshed its hold text.
- G3 — corrected document overclaims: `--plan` does create local git objects/fetch refs (it is not "writes nothing"); no separate first-parent-continuity measurement is recorded; "all 20 blocked solely by approval" overstated the six independent holds; and the post-#722 `6473bac4…` value is a trial **commit**, with tree `5a38dc10…`.
- G4 — added the missing gates: `prior_tip` sibling-blob comparison at apply time (matching plan), `dismiss_stale_reviews` as a mandatory protection gate plus a last-moment protection re-check, and rejection of `APPROVED` reviews with `commit_id=None` or a non-exact commit. `--plan` remains the default read-only mode; `--apply` still requires explicit `--distinct-approval` with no bypass, admin call, force-push or review creation.

Remaining owner action: obtain one real distinct human approving review at each exact head; then run the `--apply` command with that reviewer's login. Public release, final visual acceptance and the named holds stay owner-gated.
