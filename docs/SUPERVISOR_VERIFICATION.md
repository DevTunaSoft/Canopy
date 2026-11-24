# Canopy supervisor — verification evidence

**Verified 2026-11-21 (UTC).** This is evidence for the bounded supervisor pilot
only. It is **not** Canopy release approval, Mint acceptance, visual signoff or
permission to merge anything to `main`.

## Environment

- Host: Windows 11, PowerShell, Python 3.14 (`py -3`), Git for Windows.
- OpenCode CLI 1.19.6, authenticated `opencode-go` provider through the
  existing local installation. Worker model: `opencode-go/hy4-flash-free`.
- GitHub CLI 2.104.0, authenticated as `DevTunaSoft` with `repo` scope.
- Private disposable repository: `DevTunaSoft/canopy-supervisor-verification`
  seeded with `README.md` and `tests/test_smoke.py` at `e020b35`.
- Canopy branch under test: `feat/windows-multi-agent-supervisor-20261121`.

A private throwaway repository was used so verification PRs would not add noise
to the Canopy stacked-PR queue. No Canopy Qt, artwork or CI file was changed.

## Automated checks

| Check | Result | Command |
| --- | --- | --- |
| Supervisor unit tests | PASS — 82 tests (measured on branch HEAD `2835e880`; re-run before publication) | `py -3 -m unittest tests.test_canopy_supervisor -q` |
| Regression suite (Windows-applicable modules) | PASS — 221 tests | `py -3 -m unittest -q <all tests except three POSIX-only modules>` |
| Byte compile | PASS | `py -3 -m compileall -q canopy_supervisor tools/canopy_supervisor.py tests/test_canopy_supervisor.py` |
| Full discovery on Windows after isolation | PASS — 354 tests, 53 POSIX-only skips (measured on branch HEAD `2835e880`) | `py -3 -m unittest discover -s tests -q` |
| Canopy draft PR #135 `foundation` check | PASS — 19 s, Ubuntu, current head `2835e880` (25 s at `250257d`, superseded) | `gh pr checks 135 --repo DevTunaSoft/Canopy` |
| Canopy draft PR #135 `desktop-menu` check | PASS — 14 s, Ubuntu, current head `2835e880` (12 s at `250257d`, superseded) | `gh pr checks 135 --repo DevTunaSoft/Canopy` |

POSIX-only cases were isolated in commit `250257d`: the `geteuid` patch uses
`create=True`, Desktop Entry quoting and execute-bit cases skip on Windows, and
symlink-policy cases skip on Windows. Linux CI still runs all of them. No CI
workflow was added or duplicated by this change.

## Live coordination run

Commands (state root outside the working tree):

```powershell
py -3 tools/canopy_supervisor.py --state-root $state init --repo $e2e `
  --max-workers 3 --model opencode-go/hy4-flash-free --opencode-exe $exe `
  --repo-slug DevTunaSoft/canopy-supervisor-verification `
  --task-timeout-minutes 20 --stall-minutes 4
py -3 tools/canopy_supervisor.py --state-root $state add-task ...   # task-a, task-b, task-c
py -3 tools/canopy_supervisor.py --state-root $state check          # CHECK_PASS tasks=3
py -3 tools/canopy_supervisor.py --state-root $state run
```

Observed from `dashboard.md` / `history.jsonl`:

1. Three independent workers launched at 21:27:56–21:27:57 UTC with distinct
   PIDs (21780, 14356, 30064), workers (`worker-1..3`), worktrees
   (`state/worktrees/task-{a,b,c}`) and branches
   (`feat/canopy-supervisor-task-{a,b,c}`). Concurrency limit 3 was enforced.
2. Each worker created only its owned file (`docs/task-a.md`, `docs/task-b.md`,
   `docs/task-c.md`) and ran the real command
   `py -3 -m unittest tests.test_smoke -v`, which reported `Ran 1 test ... OK`
   in the captured log. Each wrote evidence JSON with `draft: true`.
3. At 21:28:38 UTC, task-a's worker process was killed with
   `taskkill /PID 21780 /T /F` to simulate an interrupted task. The supervisor
   logged `recovered` (`worker process lost or lease expired; task recovered`)
   and relaunched task-a on `worker-1` with PID 30712 and attempt 2. The
   checkpoint changed from `launched` to `recovered`.
4. Clean `stop`, restart and checkpoint replay were exercised. Interrupted
   tasks with evidence were replayed to verification; those without evidence
   were requeued. A limited retry budget was raised from 2 to 3 in the
   verification state because the injected kill consumed one attempt.
5. Verification rejected an out-of-scope `__pycache__` byproduct in task-a
   before commit. After cleanup, all three tasks reached `awaiting_review`.

## Draft PR evidence

| PR | Branch | Files changed | Draft |
| --- | --- | --- | --- |
| [#1](https://github.com/DevTunaSoft/canopy-supervisor-verification/pull/1) | `feat/canopy-supervisor-task-a` | `docs/task-a.md` | yes |
| [#2](https://github.com/DevTunaSoft/canopy-supervisor-verification/pull/2) | `feat/canopy-supervisor-task-b` | `docs/task-b.md` | yes |
| [#3](https://github.com/DevTunaSoft/canopy-supervisor-verification/pull/3) | `feat/canopy-supervisor-task-c` | `docs/task-c.md` | yes |

Verified with `gh pr view <n> --repo DevTunaSoft/canopy-supervisor-verification
--json isDraft,headRefName,baseRefName,files,url`. All target `main`, all are
drafts, and the file sets are disjoint. No PR was merged; the supervisor code
contains no merge operation.

## Defects found by the live run and fixed

- `step()` did not call `monitor()`, so finished workers were never verified.
  Added call plus a regression test.
- Clean-shutdown tasks were left in `interrupted` and never replayed after
  restart. Recovery now replays them to verification or the queue, or blocks
  them at the attempt limit.
- Changed-file validation inspected only committed diffs, so uncommitted work
  looked empty. It now checks pending files before commit and the real diff
  after commit, with a regression test for an out-of-scope pending file.

## Autonomous roadmap waves (actual Canopy repository)

Supervisor state root: `C:\Users\X1\AppData\Local\Temp\opencode\supervisor-canopy-state`.
Configured repo: `C:\Users\X1\Projects\Canopy`; `base_branch` is this feature
branch, so each worker PR is a bounded draft stacked on it. The live supervisor
was restarted only between waves, never while workers were running; a host
restart cancelled one idle step and recovery republished the finished worker
without losing state.

| Wave | Tasks | Worker / branch suffix | PR | Result |
| --- | --- | --- | --- | --- |
| 1 | qt-mint-evidence, visual-qa-evidence, regression-security-notes | worker-1..3 / qt-mint-evidence, visual-qa-evidence, regression-security-notes | #136, #137, #138 | awaiting_review; `foundation` PASS on each |
| 2 | qt-build-blockers-followup, visual-evidence-gaps-followup, performance-security-followup | worker-1..3 / matching suffixes | #139, #140, #141 | awaiting_review; `foundation` PASS on each |
| 3 | ci-queue-audit, recovery-evidence-followup, roadmap-handoff-summary | worker-1..3 / matching suffixes | #142, #143, #144 | awaiting_review; `foundation` PASS on each |

`history.jsonl` has exactly one `auto_queued` event per task id. All nine task
ids and branches are unique and no two task scopes conflict. No worker edited an
approved icon, dock, wallpaper, Qt GUI, workflow or supervisor source file;
each commit adds one bounded evidence document plus evidence JSON outside the
worktree. All test commands and outputs are in the per-task logs and PR bodies.

Wave 1 evidence explicitly records: no compiled Qt binary, no Qt toolchain, no
Mint VM, no compiled-Qt screenshot and no owner visual signoff. Those remain
BLOCKED/NOT RUN, not passed. Every worker PR is a draft; no PR was merged.
Human code review, owner visual approval, real Mint acceptance and required
approval stacks are not satisfied, so merging to `main` is not authorized.

## Continuous scheduling fix (after three waves)

Root cause of the idle state: the built-in roadmap was a finite six-task list.
All six tasks were consumed, so `next_tasks()` correctly returned an empty list
and the supervisor kept polling with nothing to dispatch.

Fix, on branch commit `4f77407`: `roadmap.generate()` supplies an ordered,
continuous campaign list (Qt toolchain, real source build, runtime screenshots,
icon verification, Mint acceptance, security/resource gates). Each campaign has
a hard attempt cap, failed tasks wait through exponential backoff, scope/branch
uniqueness is per attempt, and tasks with no worktree diff finish as `done`
without opening a PR. The dashboard now reports active workers, PRs, failures
and next actions.

`test_step_auto_queues_successive_unattended_cycles` drives three consecutive
unattended cycles; `test_generate_prioritizes_real_work_and_caps_campaigns`
and `test_failed_task_respects_backoff_before_redispatch` cover priority and
bounded retries. Full suite: 354 tests PASS (53 POSIX-only skips).

Live persistent supervisor: process PID `15576`, started from
`C:\Users\X1\Projects\Canopy` with
`py -3 tools/canopy_supervisor.py --state-root C:\Users\X1\AppData\Local\Temp\opencode\supervisor-canopy-state run`,
stdout/stderr redirected to
`C:\Users\X1\AppData\Local\Temp\opencode\supervisor-canopy-state\supervisor.log`.
First continuous campaign launched `qt-toolchain-enablement-attempt-1`,
`qt-source-build-attempt-1` and `qt-runtime-screenshot-attempt-1` on
`worker-1..3` in separate worktrees. When the toolchain task finished, draft PR
#145 opened (`foundation` PASS) and `original-icon-verification-attempt-1` was
queued automatically on `worker-1` with no further prompt. The supervisor was
left running; no fixed wave limit remains.

## What this does not prove

The implementation draft PR is
[#135](https://github.com/DevTunaSoft/Canopy/pull/135). No claim is made about
Linux Mint guest acceptance, real Qt screenshots, owner visual approval,
low-resource targets, Shell Pack runtime loading, or safety of any community
package. Those gates remain documented in `docs/QUALITY.md` and
`docs/RELIABILITY_99_GATE_AUDIT.md`. Green CI or a draft PR is not merge
authorization.

## Plugin verification (2026-11-21)

Host-side plugin state was checked without reinstalling or reconfiguring anything
except the reversible Ponytail mode file:

| Plugin | Evidence | Result |
| --- | --- | --- |
| Caveman | ~/.config/opencode/plugins/caveman plus MCP server ~/.caveman/bin/caveman-mcp.exe; caveman_stats returned a valid session payload; .caveman-active present | Available and functioning |
| Ponytail 5.3.3 | OpenCode plugin @dietrichgebert/ponytail cached under ~/.cache/opencode/npm/.../5.3.3; active mode switched from full to lite in ~/.config/opencode/.ponytail-active | Available; lite mode supported and selected |
| Claude Mem | MCP server ~/.claude/plugins/marketplaces/thedotmack/.../mcp-server.cjs plus plugin ~/.config/opencode/plugins/claude-mem.js; claude_mem_search("Canopy supervisor") returned 257 observations | Available and functioning |

No duplicate hook was found to be active. ~/.config/opencode/plugins/caveman-native.js
exists but is not referenced by opencode.json; it was left untouched because there is
no demonstrated runtime problem. The plugin and plugins keys in opencode.json were left unchanged because no
demonstrated loading failure or configuration drift was identified.

## Current three-worker supervisor state

The three Canopy worker tasks are complete and awaiting review:

| Task | Worker | Branch | PR | Check |
| --- | --- | --- | --- | --- |
| qt-mint-evidence | worker-1 | feat/canopy-supervisor-qt-mint-evidence | #136 | foundation PASS |
| visual-qa-evidence | worker-2 | feat/canopy-supervisor-visual-qa-evidence | #137 | foundation PASS |
| regression-security-notes | worker-3 | feat/canopy-supervisor-regression-security-notes | #138 | foundation PASS |

Distinct ownership, worktrees, branches, commits and evidence files were verified.
No worker was restarted. Qt build, Qt screenshots, and Linux Mint guest acceptance
remain blocked or not run as documented in the worker PRs; they are not claimed as
passed.
