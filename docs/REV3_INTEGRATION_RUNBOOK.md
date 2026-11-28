# Rev3 post-approval integration runbook (2026-11-28)

## Status and boundary

- Controlling goal: `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md` SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a` (short `1fba4b1e`).
- Base / known-good rollback SHA: `ec910d7a7275296ecbc8b5e5c459d356205165d1` (`integration/canopy-plasma6-20261127` live tip at drafting).
- Runbook branch: `integration/rev3-approval-runbook-20261128`, created from `ec910d7a`. It owns only `tools/integration/apply_rev3_approval_runbook.py`, `docs/REV3_INTEGRATION_RUNBOOK.md` and `scratch/rev3_integration_runbook/**`.
- **This runbook did not merge, approve, edit, promote or comment on any PR.** It did not change any protection setting, global config, visual asset, named hold (#151/#278/#279) or security/release gate. Its only remote mutation is pushing its own runbook branch. (Creating this remediation worktree is a local checkout change, not a remote or PR mutation.)
- At drafting, all 14 original candidates were mergeable with 3/3 terminal `success` checks at their exact heads and no approving review; green CI is evidence, not authorization. The 2026-11-28 extension covers #751-#758 at fresh live pins: seven more PRs join the ordered chain (#751, #752, #753, #754, #755, #757, #756) and #758 is held for an unresolved overlap with #746. Eight PRs in total are held for independent reasons (below), not merely for lack of approval.
- Project-scoped concurrency cap is 8 Canopy/LacOS subagents plus Hermes; 6 slots were occupied at extension time. No worker was spawned, reassigned or interrupted for this extension.

## Live evidence captured at drafting (UTC 2026-11-28T08:10:19Z) and extension probe (2026-11-28T10:44Z)

- Integration and `main` protection: `required_approving_review_count=1`, `dismiss_stale_reviews=true`, `enforce_admins.enabled=true`, `strict=true`, required contexts `foundation`, `qt-evidence`, `fake-gio-launch-fixture`.
- Every plasma-base PR base ref/sha = `integration/canopy-plasma6-20261127` / `ec910d7a…`; all 28 heads pinned in the script; all 28 file-path sets pinned by count and SHA-256. The added pins are the live heads observed at the extension probe; #755 and #758 were re-pinned during that probe to `b5fd0b83…` and `65896566…`. #758 was subsequently re-pinned again to live head `32cc8e0b6a90f644f150419c9a34e93aab278c16` after a post-drift fix (same 15 paths, same paths SHA-256), and then re-pinned again to the current live head `a1122a2f8d558aef727c4481d05a141075d06cfc` for the owner G4 verification (still the same 15 paths and paths SHA-256). Both earlier values are historical evidence only.
- Raw curated probes: `scratch/rev3_integration_runbook/evidence/live_state_20261128.json`, `protection_20261128.json`, `trial_merge_20261128.json`, `decisions_20261128.json`, `pr750_conflict_20261128.txt`, plus the remediation re-pin probe `repin_749_20261128.json` and the extension probes `live_state_751_758_20261128.json`, `mutex_conflicts_751_758_20261128.json`, `conflicts_751_758_20261128.txt` (with the re-pinned-head recheck); directory verified with `SHA256SUMS.txt` (11 entries, including the G4 re-pin probe `repin_758_a1122a2f_20261128.json`).

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

## Exact dependency-ordered merge sequence (21 merges)

| # | PR | Exact head | Depends on | Reason |
|---|----|------------|------------|--------|
| 1 | #722 | `035fa9c2d00e6f8a0dde7ca70036049010ac436b` | — | Governing architecture (Rev3 A2.1); owns four instruction files |
| 2 | #741 | `ba1994b835308132ac964520ffcbe032923c177c` | #722 | Installable native Plasma 6 development baseline (A2.2) |
| 3 | #733 | `a0b1c77b94bd0cb3b341a472f68de596ff5f6dce` | #741 | Real rollback proof closes B01 gaps against the #741 install baseline |
| 4 | #737 | `35c1fe7a0c76cc3dbebe9e3f633b587cbfc377e6` | #741 | Approved dock geometry 32/96/14/7 port with synced test pins |
| 5 | #736 | `df73dfb6d1272b72e1f57b3b57539373c05dd636` | #741 | Host-event limiter/epoch ceilings for reliable native events |
| 6 | #732 | `a14e335a75f35f775bcd669de4e2ba5ab173168c` | #736, #737 | Bounded native quick controls with truthful PASS/NOT_RUN labels |
| 7 | #752 | `9e2051c9581226f5807f007975fc411bfca72e08` | #732 | QML secondary-label names and compact Window/Help reachability (re-pinned to live head; 17 paths) |
| 8 | #755 | `b5fd0b8337322d292e8f9c55bbedbb03fd9cab94` | #752 | Root-caused Classic a11y labels; completes #752's out-of-ownership hunks |
| 9 | #735 | `349742749a4ab9dbf2903df876e3d9b70e299986` | #737 | Native Konsole launch from the restored Terminal dock tile |
| 10 | #745 | `80097f8b97b7d5df35b4e53bb9cd835b546aca9f` | #735 | Native launcher search over the same upstream desktop catalog |
| 11 | #743 | `2b8bca910d84b19966b29db37dfb3ce7512e810f` | #745 | Bounded KWin/window/workspace decision boundary |
| 12 | #744 | `2733f7e09e0e3447fe39eebce6a71171e2ebf476` | #743 | Session settings persistence and crash recovery |
| 13 | #748 | `9f766d06225f4a7e7cfe9be010a3432a4109ea05` | #744 | Fail-closed suspend/resume verdicts over recovered session state |
| 14 | #740 | `f8ba8187bc67b8bf1de49c4e40977f33e17d6e74` | #744 | Native AT-SPI role vocabulary and scoped verification |
| 15 | #746 | `050853173419c7224ab8875233f5ef1d7aea622c` | #744 | Bounded display response for monitor add/remove and HiDPI |
| 16 | #747 | `ca378da2c2b116db8ce79dc711001add9af59897` | #741 | Notifications/tray reusing the single upstream Plasma owner |
| 17 | #751 | `813ec445f042049615e4ed5c02f9a4831a2aba83` | — | Bounded first-party Modern Shell Pack metadata; disjoint from all others |
| 18 | #753 | `616ce171a7b71f69f19060122f53c97ada346662` | — | Bounded LacOS P0 software-source manifest and read-only probes |
| 19 | #754 | `56dbb99b7ed6d62140b17b9abfba79231f9cbe96` | — | Compiled native display/DPI host bridge over the shared contract |
| 20 | #757 | `4e4471a5c3719041353c432653f1bf0986091815` | #748 | Read-only suspend/resume recovery contract; historical add/add resolved by rename |
| 21 | #756 | `b88f07c7db27546d425445c1b693d97292cbae3c` | all above | Verified native dev-artifact consolidation; must be last |

The dependency list is topological and asserted by `--self-test`, including the extension's `#752 -> #755`, `#748 -> #757` and `#756`-last constraints. `#750` depends on `#722` by file overlap but is held (below); `#741` therefore follows `#722` directly. `#757` previously add/add-conflicted with `#748` at head `50cc4023…` on `docs/NATIVE_SUSPEND_RESUME.md`; its live head renames that path to `docs/NATIVE_SUSPEND_RESUME_CONTRACT.md` and the exact-SHA trial merge is clean, so it is ordered after `#748`. `#758` still conflicts with `#746` and is held.

## Skipped PRs (re-derived live at plan time; holds remain authoritative)

| PR | Reason |
|----|--------|
| #734 | Body still pins stale head `93c4dbc8` while live head is `bd67e735…`; native runtime `NOT_RUN/BLOCKED`; body states "No merge is requested or authorized by this PR". |
| #738 | `BASELINE_CAPTURED_NOT_ACCEPTED`; executed-binary hash withdrawn as `EVIDENCE_GAP`; no accepted increment. |
| #739 | `INCOMPLETE_600S_CAP` (no terminal full-suite verdict) and `NO_COMPILED_SWITCHER_WIRING`. |
| #742 | Independent review requires two documentation corrections before promotion; `stage_06_verify.log` and `board_probe.log` are ABSENT at the exact head and the "37 tests" claim has no artifact. |
| #749 | Re-pinned to live head `f8cbe123ba2a88edbdc509c5dd8ebe9e20b85260` (sampler/report remediated); body still says "no merge, no self-approval, no ready-for-merge promotion; independent review only"; machine verdict `SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT`. |
| #750 | `OVERLAP_HOLD`: shares `.github/PULL_REQUEST_TEMPLATE.md`, `AGENTS.md`, `docs/AGENTS_WORKFORCE.md`, `docs/ROADMAP.md` with #722. Trial merge onto the post-#722 trial tree conflicts in all four files (`pr750_conflict_20261128.txt`). Requires an authorized re-pin onto the post-#722 tip, a fresh independent review and 3/3 checks at the new head. The external Rev3 directive SHA remains controlling in the meantime. No PR edit is performed by this runbook. |
| #758 | `OVERLAP_HOLD`: re-pinned to live head `a1122a2f8d558aef727c4481d05a141075d06cfc` (15 paths, unchanged paths SHA-256). It changes `canopy_features/dock/display_change_response.py` and `docs/NATIVE_DISPLAY_RESPONSE.md`, both already changed by ordered #746. Exact-SHA trial merge conflicts with #746 even when sequenced after it (`conflicts_751_758_20261128.txt`, rc=1 re-verified at the new head). #746 stays in ORDER; #758 needs an explicit integrator decision or an authorized combined implementation with fresh review and 3/3 checks at the new head. |

A hold that appears cleared live is still skipped: re-baselining needs a new authorized review, not an automatic promotion. `#757` is the deliberate exception: its conflict was resolved by the author at the exact live head that is pinned here, and the exact-SHA trial chain proves compatibility; no PR edit was made by this runbook.

## Mutual exclusion and conflict policy

- `#721` and `#723` (legacy base `integration/canopy-classic-20261123`) share 9 paths; `#724` and `#728` share 4 (`mutex_conflicts_751_758_20261128.json`). Each pair is mutually exclusive: at most one member may be promoted into one chain. Neither pair is in `ORDER`; `MUTEX_GROUPS` and `--self-test` enforce this.
- `#748` vs `#757`: historical add/add conflict on `docs/NATIVE_SUSPEND_RESUME.md` at `#757` head `50cc4023…` (merge-tree rc=1). The pinned live head `4e4471a5…` renames the file; the exact-SHA trial merge is clean. `RESOLVED_CONFLICTS` records this, and `#757` is ordered immediately after `#748`.
- `#746` vs `#758`: unresolved overlapping-path conflict on `canopy_features/dock/display_change_response.py` and `docs/NATIVE_DISPLAY_RESPONSE.md`; exact-SHA trial merge fails. `CONFLICT_HOLDS = {758: 746}`; `#746` remains ordered, `#758` is held.
- No PR was merged, approved, edited, commented on or promoted by this extension. The only remote mutation is the push of the runbook branch itself.

## Trial merge result validation

For each candidate, after live checks pass:

```bash
git fetch --no-tags origin pull/<n>/head:refs/rev3-runbook/pr-<n>
git merge-tree --write-tree --merge-base ec910d7a7275296ecbc8b5e5c459d356205165d1 \
    <evolving-trial-tip> <exact-pr-head>
git diff --name-status <trial-tip> <trial-tree>
```

The script refuses on non-zero rc, conflict markers, any net path outside the PR's pinned file set, workflow/unowned protected paths, or a sibling path whose blob changed between the prior and current trial tip. The `prior_tip` sibling comparison runs in `--plan` **and** `--apply`; `apply` uses the evolving trial commit from the preceding PR, not just the live tip. `--merge-base` is pinned to `ec910d7a` because this checkout is shallow; every pinned PR branches from that base. The trial commit is a local `commit-tree` object only — no ref, branch, PR or remote is changed by the trial itself (the separate `fetch` step does create local `refs/rev3-runbook/*`).

Observed at drafting: **14/14 trial merges clean**; #750 conflicts on the four shared instruction files and is held. The post-#722 **trial commit** was `6473bac4afd674429e087bd2fff6c001e7f45a5d`; its **tree** was `5a38dc10cc9293fa37471329d6ba2d06132ab83d`. A commit SHA and a tree SHA are different objects and are labelled separately in evidence (`trial_commit` vs `tree`/`trial_tree`). After extension: **21/21 trial merges clean** in the table order (including all seven newly ordered PRs); #758 conflicts with #746 and is held (`conflicts_751_758_20261128.txt`). File lists are read with REST pagination so #756's 469 paths are all checked; a single-page read would falsely report scope drift.

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

## Extension verification (#751-#758, branch head 7765ec8 base)

- `python tools/integration/apply_rev3_approval_runbook.py --self-test` → `SELF_TEST_PASS gates=checks+approval+graphql-decision+commit-id+dismiss-stale+order+skip-disjointness+pin-shape+apply-sibling+mutex+conflict-holds+resolved-add-add+new-pins`, rc=0: 21 ordered, 7 skipped, 28 pins complete and disjoint; legacy mutex pairs absent from ORDER; `#757` follows `#748` and `#756` follows all merges; exact new head pins asserted.
- `python tools/integration/apply_rev3_approval_runbook.py --plan` → `PLAN_ONLY_DISTINCT_APPROVAL_PENDING`, live tip equals `ec910d7a…`, both protections `PASS`, **21/21 TRIAL_CLEAN**, 7 skip holds re-derived live `True`. No PR, branch, protection or remote state was mutated.
- Live probe: all eight PRs have `baseRefOid = ec910d7a…`, 3/3 terminal `success` contexts at their pinned heads and `reviewDecision = REVIEW_REQUIRED`; #755 and #758 were re-pinned after an observed head advance. No approval exists or was created.
- Conflict evidence: `#757` add/add conflict at historical head `50cc4023…` (rc=1) versus clean trial at pinned head `4e4471a5…`; `#758` still conflicts with `#746` (rc=1).

## Remediation of review holds G1–G4 (branch head 166546a)

- G1 — replaced the REST `review_decision` gate (always `None` on REST pull objects) with a live GraphQL `reviewDecision` query, cross-checked against `headRefOid`; fail closed on query errors, null decisions or head drift.
- G2 — re-pinned #749 to `f8cbe123…` with a live-derived file count/path digest, and refreshed its hold text.
- G3 — corrected document overclaims: `--plan` does create local git objects/fetch refs (it is not "writes nothing"); no separate first-parent-continuity measurement is recorded; "all 20 blocked solely by approval" overstated the six independent holds; and the post-#722 `6473bac4…` value is a trial **commit**, with tree `5a38dc10…`.
- G4 — added the missing gates: `prior_tip` sibling-blob comparison at apply time (matching plan), `dismiss_stale_reviews` as a mandatory protection gate plus a last-moment protection re-check, and rejection of `APPROVED` reviews with `commit_id=None` or a non-exact commit. `--plan` remains the default read-only mode; `--apply` still requires explicit `--distinct-approval` with no bypass, admin call, force-push or review creation.

Remaining owner action: obtain one real distinct human approving review at each exact head; then run the `--apply` command with that reviewer's login. Public release, final visual acceptance and the named holds stay owner-gated.

## #758 re-pin remediation (post-drift fix, 2026-11-28T12:46Z)

- Live `gh pr view 758` / `gh api pulls/758` reported head `32cc8e0b6a90f644f150419c9a34e93aab278c16` on `product/native-multimonitor-20261128`, base `ec910d7a…`, state OPEN, `baseRefOid` still `ec910d7a…`. The stale `65896566…` pin was replaced in both `PINS[758]` and the self-test assertion; the 15 file paths and their SHA-256 (`90a6d8a2…`) are unchanged.
- Live checks at the new head: `foundation`, `qt-evidence`, `fake-gio-launch-fixture` all `completed/success`; GraphQL `reviewDecision=REVIEW_REQUIRED` with `headRefOid` equal to the new head; `mergeable=true`, `mergeable_state=blocked`. The body still carries the explicit integrator-choice hold. No approval exists or was created.
- Conflict recheck: exact-SHA `git merge-tree` of the new #758 head against ordered #746 (live head `05085317…`, merge base `ec910d7a…`, and the post-#754 trial tip `cf3af8a2…`) returns rc=1 on `canopy_features/dock/display_change_response.py` and `docs/NATIVE_DISPLAY_RESPONSE.md`. #746 stays in ORDER, #758 stays SKIPPED; evidence appended to `conflicts_751_758_20261128.txt` and sealed in `repin_758_20261128.json`.
- `python tools/integration/apply_rev3_approval_runbook.py --self-test` → `SELF_TEST_PASS …` rc=0: 28 pins, 21 ordered, 7 skipped, order/skip disjointness, topological deps, mutex pairs, conflict holds, resolved add/add, `#756` last and all protection/approval/trial gates intact.
- Fresh `python tools/integration/apply_rev3_approval_runbook.py --plan` at live heads (generated `2026-11-28T12:46:48Z`): `PLAN_ONLY_DISTINCT_APPROVAL_PENDING`, live tip `ec910d7a…`, both protections `PASS` with `dismiss_stale_reviews=true`, **21/21 `TRIAL_CLEAN`** and zero candidate problems, **7/7 skip holds re-derived live `True`**. #746 is `TRIAL_CLEAN`; #758 is absent from the sequence and skipped. No PR, branch, protection or remote state was mutated by the plan.
- No merge, approval, review creation, PR edit or protection change was performed. The only remote mutation is the push of this runbook branch with the re-pin.

## Owner G4 re-verification re-pin (2026-11-28T15:45Z)

- Owner action summary verification G4 found this runbook still pinning #758 to `32cc8e0b6a90f644f150419c9a34e93aab278c16` while the live head had advanced; a future plan would have failed `verify_skip_reason` and dropped the #758 hold re-derivation. `PINS[758]`, `SKIP[758]` and the self-test assertion now use the live head `a1122a2f8d558aef727c4481d05a141075d06cfc`. The 15 paths and their SHA-256 (`90a6d8a2…`) are byte-identical to the previous pin; `foundation`, `qt-evidence` and `fake-gio-launch-fixture` are `completed/success` at the new head; GraphQL `reviewDecision=REVIEW_REQUIRED` with `headRefOid` equal to the new head; `mergeable=true`, `mergeable_state=blocked`; the body still carries the integrator-choice hold. #746 remains ordered and #758 remains skipped.
- Conflict recheck at the new head: exact-SHA `git merge-tree` returns rc=1 on `canopy_features/dock/display_change_response.py` and `docs/NATIVE_DISPLAY_RESPONSE.md` both against #746's live head `05085317…` and against the post-#754 trial tip `cf3af8a2…`; appended to `conflicts_751_758_20261128.txt` and sealed in `repin_758_a1122a2f_20261128.json`.
- A first fresh plan exposed an independent earlier advance of **#752** (pushed 14:42:54Z) as `HEAD_DRIFT+SCOPE_DRIFT`, which reduced that run to 20/21 trial. Its live pin was therefore also refreshed from `906181cd…` (16 paths) to `9e2051c9581226f5807f007975fc411bfca72e08` (17 paths, paths SHA-256 `5784e863…`), with 3/3 terminal `success` checks and `reviewDecision=REVIEW_REQUIRED` at the new head. #752 stays in ORDER immediately before #755; no skip count or dependency changed.
- `python tools/integration/apply_rev3_approval_runbook.py --self-test` → `SELF_TEST_PASS …+skip758-head-rederive`, rc=0: 28 pins, 21 ordered, 7 skipped, order/skip disjointness, topological deps, mutexes, conflict holds, `#756` last, GraphQL/decision/commit-id/dismiss-stale gates, and a new offline assertion that the #758 hold re-derives `True` at the exact pin and `False` on head drift.
- Fresh `python tools/integration/apply_rev3_approval_runbook.py --plan` (generated `2026-11-28T15:45:18Z`; evidence `scratch/rev3_integration_runbook/runs/20261128T154518Z/run.json` with `SHA256SUMS.txt`): `PLAN_ONLY_DISTINCT_APPROVAL_PENDING`, live tip `ec910d7a…`, both protections `PASS` with `dismiss_stale_reviews=true`, **21/21 `TRIAL_CLEAN`**, zero candidate problems, all 21 candidate heads equal to their pins, **7/7 skip holds re-derived live `True`**. #746 is `TRIAL_CLEAN`, #752 is `TRIAL_CLEAN`, and #758 is absent from the sequence.
- No merge, approval, review creation, PR edit, protection change or bypass was performed. `--plan` remains the default read-only mode and `--apply` still requires explicit `--distinct-approval`; the only remote mutation is the push of this runbook branch with the re-pins.
