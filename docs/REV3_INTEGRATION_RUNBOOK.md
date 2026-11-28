# Rev3 post-approval integration runbook (2026-11-28)

## Status and boundary

- Controlling goal: `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md` SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a` (short `1fba4b1e`).
- Base / known-good rollback SHA: `ec910d7a7275296ecbc8b5e5c459d356205165d1` (`integration/canopy-plasma6-20261127` live tip at drafting).
- Runbook branch: `integration/rev3-approval-runbook-20261128`, created from `ec910d7a`. It owns only `tools/integration/apply_rev3_approval_runbook.py`, `docs/REV3_INTEGRATION_RUNBOOK.md` and `scratch/rev3_integration_runbook/**`.
- **No PR was merged, approved, edited, promoted or commented on.** No protection setting, worktree assignment, global config, visual asset, named hold (#151/#278/#279) or security/release gate was changed. The only remote mutation is pushing this runbook branch.
- All 20 candidate PRs were blocked solely by the missing distinct human approving review: live `mergeable=true`, `mergeStateStatus=BLOCKED`, `reviews=[]`, 3/3 terminal `success` checks at every exact head. Green CI is evidence, not authorization.

## Live evidence captured at drafting (UTC 2026-11-28T08:10:19Z)

- Integration and `main` protection: `required_approving_review_count=1`, `dismiss_stale_reviews=true`, `enforce_admins.enabled=true`, `strict=true`, required contexts `foundation`, `qt-evidence`, `fake-gio-launch-fixture`.
- Every PR base ref/sha = `integration/canopy-plasma6-20261127` / `ec910d7a…`; all 20 heads pinned in the script; all 20 file-path sets pinned by count and SHA-256.
- Raw curated probes: `scratch/rev3_integration_runbook/evidence/live_state_20261128.json`, `protection_20261128.json`, `trial_merge_20261128.json`, `decisions_20261128.json`, `pr750_conflict_20261128.txt`; directory verified with `SHA256SUMS.txt`.

## Execution gate (mandatory)

```bash
cd C:/Users/X1/Projects/Canopy
python tools/integration/apply_rev3_approval_runbook.py --self-test
python tools/integration/apply_rev3_approval_runbook.py --plan
# ONLY after a real distinct human APPROVED review exists at the exact head:
python tools/integration/apply_rev3_approval_runbook.py --apply --distinct-approval <human-login>
```

- `--plan` (default) is read-only: live re-query, per-PR gate evaluation and sequential trial merges; it writes nothing to the repository.
- `--apply` **refuses without `--distinct-approval <login>`** and refuses when the login is the PR author (`DevTunaSoft`) or a bot, when no `APPROVED` review from that login exists at the exact head, when `reviewDecision != APPROVED`, or when `mergeStateStatus` is still `BLOCKED`.
- Protection is re-queried at apply time. A missing/changed protection API, weaker review requirement, disabled `enforce_admins`, non-strict checks or changed required contexts refuses the run.
- The only merge call is the ordinary GitHub merge API (`PUT /pulls/<n>/merge` with `merge_method=merge` and the exact head `sha`). There is **no** admin endpoint, `--admin`, force-push, reset, review creation, self-approval or PR edit anywhere in the script.
- Head/base/scope/check drift, non-mergeable or conflicting state, unexpected protected/workflow paths, a dirty trial merge, a live tip that advanced before the merge, or a post-merge regression stop the chain and write refusal evidence to `scratch/rev3_integration_runbook/runs/<UTC>/run.json` with a `SHA256SUMS.txt` sidecar.

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
| #749 | "No merge, no self-approval, no ready-for-merge promotion; independent review only"; machine verdict `SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT`. |
| #750 | `OVERLAP_HOLD`: shares `.github/PULL_REQUEST_TEMPLATE.md`, `AGENTS.md`, `docs/AGENTS_WORKFORCE.md`, `docs/ROADMAP.md` with #722. Trial merge onto the post-#722 tree conflicts in all four files (`pr750_conflict_20261128.txt`). Requires an authorized re-pin onto the post-#722 tip, a fresh independent review and 3/3 checks at the new head. The external Rev3 directive SHA remains controlling in the meantime. No PR edit is performed by this runbook. |

A hold that appears cleared live is still skipped: re-baselining needs a new authorized review, not an automatic promotion.

## Trial merge result validation

For each candidate, after live checks pass:

```bash
git fetch --no-tags origin pull/<n>/head:refs/rev3-runbook/pr-<n>
git merge-tree --write-tree --merge-base ec910d7a7275296ecbc8b5e5c459d356205165d1 \
    <evolving-trial-tip> <exact-pr-head>
git diff --name-status <trial-tip> <trial-tree>
```

The script refuses on non-zero rc, conflict markers, any net path outside the PR's pinned file set, workflow/unowned protected paths, or a sibling path whose blob changed between the prior and current trial tip. `--merge-base` is pinned to `ec910d7a` because this checkout is shallow; every pinned PR branches from that base. The trial commit is a local `commit-tree` object only — no ref, branch, PR or remote is changed.

Observed at drafting: **14/14 trial merges clean**; #750 conflicts on the four shared instruction files and is held. The post-#722 tree was `6473bac4afd6…`.

## Post-merge checks and regression stop

After each ordinary merge the script:

1. Re-queries the merge commit and polls `foundation`, `qt-evidence`, `fake-gio-launch-fixture` at the new integration tip to terminal success (bounded polls, configurable `--poll-attempts`/`--poll-interval`).
2. Creates a fresh temporary checkout pinned to the exact merge SHA (`git init`, depth-1 fetch, detached checkout) and runs `python tools/check_foundation.py`.
3. Runs `python -m unittest discover -s tests`, parsing the terminal `Ran N tests` summary from stdout **and** stderr; `FAILED` or a non-terminal summary is a regression. `--foundation-only` deliberately records `NOT_RUN`, stops the chain and does not authorize the next merge.
4. Writes per-step JSON evidence (merge SHA, first-parent continuity, check polls, logs, verdict) and a directory `SHA256SUMS.txt` under `scratch/rev3_integration_runbook/runs/<UTC>/`.

Any regression stops dependent integrations immediately; unaffected independent work is not touched by this script.

## Known-good rollback

- Known-good SHA: `ec910d7a7275296ecbc8b5e5c459d356205165d1`.
- Verify: `git ls-remote origin refs/heads/integration/canopy-plasma6-20261127` (must equal the known-good SHA before the first merge).
- On regression: stop, capture evidence, then restore by `git revert -m 1 <merge_sha>` for merged commits **in reverse order**, each through a new independently reviewed PR with the same distinct-human approval and protection gates; rerun foundation + full suite at the restored tip.
- Forbidden: force-push, `git reset --hard` on the integration branch, admin bypass, self-approval, history rewriting. The script only emits the rollback plan; it never executes a revert.

## Verification performed for this runbook

- `python tools/integration/apply_rev3_approval_runbook.py --self-test` → `SELF_TEST_PASS` (check normalization, distinct-human approval incl. author/bot/stale-head negatives, topological order, skip/order disjointness and pin shape).
- `python tools/integration/apply_rev3_approval_runbook.py --plan` → `PLAN_ONLY_DISTINCT_APPROVAL_PENDING`; 14 `TRIAL_CLEAN`; 6 skip holds re-derived live; both branch protections `PASS`.
- `python tools/integration/apply_rev3_approval_runbook.py --apply` (no flag) → `REFUSED: DISTINCT_APPROVAL_FLAG_REQUIRED`, rc=3, no merge attempted.
- `python tools/integration/apply_rev3_approval_runbook.py --apply --distinct-approval fake-human` → refused at PR #722 with `DISTINCT_APPROVAL_NOT_VERIFIED`, `REVIEW_DECISION_NOT_APPROVED`, `STILL_BLOCKED_BY_PROTECTION`; no merge attempted.

Remaining owner action: obtain one real distinct human approving review at each exact head; then run the `--apply` command with that reviewer's login. Public release, final visual acceptance and the named holds stay owner-gated.
