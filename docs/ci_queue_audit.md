# CI and review queue ownership audit

## Scope

Read-only audit of the Canopy CI supervisor and its scheduled workflow.
No CI supervisor file, workflow, artwork, dock icon, wallpaper, Qt GUI file,
or any protected path was edited. Only `docs/ci_queue_audit.md` was written.

- Branch: `feat/canopy-supervisor-ci-queue-audit`
- Inspected worktree HEAD: `dfa57c97573203af4a4abb2d6a75da2a4f72b908`
- Read once: `AGENTS.md`, `docs/QUALITY.md`
- No full git history and no complete open-PR list were loaded.

## Files inspected (unchanged)

- `tools/review_supervisor.py` — read-only GitHub PR/CI supervisor.
  It produces a review queue from bounded, read-only API snapshots. It never
  merges, posts, assigns, approves, or executes PR code. The token scopes are
  read-only. API paths are fixed to one repo and reject untrusted input.
  Head SHAs are validated before use. Responses are size-bounded.
- `.github/workflows/review-supervisor.yml` — scheduled/dispatch/push workflow.
  Permissions are read-only (`contents`, `actions`, `checks`, `issues`,
  `pull-requests`). Steps: validate regression tests, generate report, upload
  artifact. No write or merge step exists.

## Regression tests — real output

Command run from the worktree root (the exact command used by the workflow):

```
python -m unittest tests.test_review_supervisor -v
```

Result: PASS. Exit code `0`. `24` tests ran; all `ok`; final line `OK`.
Environment: Python `3.12.10`, Windows worktree. Timing varied by run
(`0.015s` and `0.016s` observed); the clean captured run reported `0.016s`.

Excerpt (verbatim, stdout captured via stderr redirect; unittest writes to
stderr):

```
----------------------------------------------------------------------
Ran 24 tests in 0.016s

OK
```

Note: `SUPERVISOR_FAIL: GITHUB_TOKEN not supplied` appears on stderr during
`test_unauthenticated_cli_fails_closed`. That is the expected fail-closed
behaviour asserted by the test, not a failure. PowerShell 5.1 wraps native
stderr in a `NativeCommandError` line; that wrapper is a shell artifact, not
a test result.

The scheduled workflow itself was NOT executed: it requires a live
`GITHUB_TOKEN` and network access to `DevTunaSoft/Canopy`. No live report was
generated, and no claim about the current state of remote PRs is made here.

## Green CI is not merge authorization

The tests and the tool encode this explicitly, not by convention:

- `check_summary` labels even fully passing required checks as
  `REQUIRED CHECKS PASSED (NO MERGE AUTHORITY)`.
- A single successful check is labelled `SINGLE CHECK SUCCESS (REQUIRED
  COVERAGE UNKNOWN; NOT APPROVAL)`.
- Skipped-only, neutral-only, in-progress, failed, and missing-check data are
  never treated as green.
- `classify` can return `REQUIRED CHECKS PASSED / HUMAN REVIEW REQUIRED`,
  `DRAFT / REVIEW REQUIRED`, `VISUAL REJECTED`,
  `STACKED / REBASE REVIEW`, and `REVIEW / CI REQUIRED`. It never returns
  "safe to merge".
- The generated report states passing CI is not code review, visual approval,
  Linux Mint acceptance, or permission to merge.

Therefore a green badge in CI is evidence of test passing only. It is not a
merge authorization. Merge still requires a real human reviewer, visual
acceptance, Linux Mint/runtime evidence, and branch-protection decisions
recorded outside this workflow. `docs/QUALITY.md` reinforces this: never turn
a single green workflow into a release claim.

## No workflow duplication

`.github/workflows/` contains exactly three files:

```
classic-user-menu.yml
foundation.yml
review-supervisor.yml
```

Only `review-supervisor.yml` implements the review queue. A search for
`review.supervisor` / `review_supervisor` across all workflow files matched
only inside `review-supervisor.yml`. No second or duplicate supervisor or
review-queue workflow was created or found.

## Status

| Item | Result |
| --- | --- |
| Read AGENTS.md and QUALITY.md once | PASS |
| Inspect supervisor and workflow without editing | PASS |
| Regression tests (`python -m unittest tests.test_review_supervisor -v`) | PASS (24 tests, OK) |
| Live scheduled workflow execution | NOT RUN (no token/network snapshot in this task) |
| Green CI documented as non-authorizing | PASS |
| Workflow duplication check | PASS (no duplicate found) |
| Edits limited to owned path | PASS |

`draft: true` — this is an audit note, not a merge request. The supervisor
publishes; this task performs no commit, push, PR, merge, or branch change.

Path note: the objective names `docs/CI_QUEUE_AUDIT.md` while the owned path
lists `docs/ci_queue_audit.md`. On this Windows filesystem these resolve to the
same file; the tracked/owned lowercase path was kept. No second doc was created.
