# Canopy multi-agent supervisor (bounded pilot)

**Status: implementation under verification.** A passing unit test is not proof
that workers ran, recovered, or produced a real draft PR. See
[verification evidence](SUPERVISOR_VERIFICATION.md) for exact commands and
results. This document supplements, and does not replace, `AGENTS.md`,
`README.md`, `docs/ARCHITECTURE.md`, `docs/QUALITY.md` and the coordination
ledger proposed in PR #133.

## What it is

`canopy_supervisor` is a Windows-compatible, standard-library-only coordinator
for up to three independent OpenCode coding workers. Each worker runs in its
own Git worktree and feature branch. The supervisor owns the durable queue,
worker leases, scope ownership, watchdogs, evidence checks, commits, pushes and
draft PR creation.

It is **not** a replacement for the existing read-only CI supervisor in
`.github/workflows/review-supervisor.yml` or `tools/review_supervisor.py`.
That workflow keeps reporting PR/CI status with read-only permissions. This
supervisor does not add, edit or duplicate a GitHub Actions workflow.

It is **not** a merge bot. There is no merge, approval, force-push or label
operation anywhere in the implementation. A draft PR is the terminal publish
action and always requires human review.

## Safety invariants

1. One supervisor per state root. An OS file lock (`msvcrt` on Windows,
   `flock` on POSIX) is released by the OS if the process crashes.
2. Task state is small atomic JSON with `fsync` before rename. Events are an
   append-only JSONL history. A corrupt `tasks.json` stops the supervisor
   instead of being silently overwritten.
3. A task declares owned path patterns. Overlapping scopes with an active
   worker prevent assignment. Dependencies must reach `awaiting_review` or
   `done` before a dependent task runs.
4. Protected paths cannot be placed in task scope: approved icon assets,
   dock/wallpaper/Qt GUI implementation, `AGENTS.md`, the read-only supervisor
   and its CI workflow. Worker prompts repeat the same restriction.
5. Evidence is a claim. Before publishing, the supervisor checks that at
   least one test reported `PASS`, no test reported `FAIL`, the draft flag is
   true, the changed-file list matches the owned scope and contains no
   protected path, and the real git diff matches the claim.
6. Workers never commit, push or open PRs. Only the supervisor does, after
   verification.
7. Logs strip ANSI escapes and known credential shapes. Tokens are read from
   the existing authenticated OpenCode installation and passed only through
   the child process environment.

## Windows setup

Prerequisites:

- Python 3.11+ on `PATH` (`py -3 --version`).
- Git with working HTTPS credentials; `git status` in the target repo is clean.
- GitHub CLI authenticated with `repo` scope: `gh auth status`.
- An authenticated OpenCode installation. The worker reads its active
  `opencode` credential from `~/.local/share/opencode/opencode.db`
  (`C:\Users\<you>\.local\share\opencode\opencode.db` on Windows) or from
  `OPENCODE_API_KEY`. Verify with `opencode --version` and a single
  `opencode run --model opencode-go/<model>` smoke prompt before scheduling.
- The `opencode-go` provider configured in `%USERPROFILE%\\.config\\opencode\\opencode.json`.
  No new credentials are created by this supervisor.

Each worker gets its own `XDG_DATA_HOME` under the state root. This isolates
sessions and avoids colliding with the desktop OpenCode database.

## First session (PowerShell)

```powershell
Set-Location 'C:\path\to\Canopy'
git fetch origin
git switch main
git pull --ff-only origin main
py -3 -m unittest tests.test_canopy_supervisor -v

$state = 'C:\CanopySupervisor\state'
$repo = 'C:\path\to\Canopy'
$exe = 'C:\Users\<you>\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe'

py -3 tools/canopy_supervisor.py --state-root $state init `
  --repo $repo --max-workers 3 `
  --model opencode-go/hy4-flash-free --opencode-exe $exe `
  --repo-slug DevTunaSoft/Canopy --task-timeout-minutes 45 --stall-minutes 6

py -3 tools/canopy_supervisor.py --state-root $state add-task `
  --id bounded-task --title "Add a bounded note" `
  --objective "Create docs/bounded-task.md with one paragraph. Run the relevant unittest and record the real result." `
  --scope docs/bounded-task.md

py -3 tools/canopy_supervisor.py --state-root $state check
py -3 tools/canopy_supervisor.py --state-root $state run
```

Keep the state root outside the working tree in production. The default is
`./.canopy-supervisor`, which this branch adds to `.gitignore`.

## Operations

| Command | Effect |
| --- | --- |
| `status` | Print the Markdown dashboard (queue, workers, checkpoints, blockers, events). |
| `status --json` | Print raw durable task state. |
| `run` | Loop under the exclusive lock; dispatch, monitor, verify and publish. |
| `run --once` | One coordination step; used for diagnostics and tests. Does not kill live workers. |
| `feed` | Enqueue the next approved roadmap tasks once, under the same lock. |
| `autofeed` | Continuously refill the pipeline; safe to run beside an existing supervisor. |
| `pause` / `resume` | Stop or allow new dispatch; running workers continue. |
| `stop` | Request clean shutdown after the current step; checkpoints active tasks. |
| `recover` | Requeue tasks whose lease or worker process was lost. |
| `prune` | Remove worktrees of terminal tasks; history and branches remain. |
| `check` | Validate queue invariants without launching anything. |

## Autonomous task waves

With no `roadmap.json`, the supervisor uses an ordered, continuous campaign
list: Qt toolchain enablement, real source compilation, runtime screenshots,
original-icon verification, Mint acceptance and offline security/resource gates.
Documentation is only the evidence format, not the goal. Each step refills the
pipeline to `max_workers` non-terminal tasks, so the next campaign starts as
soon as a worker finishes. Every campaign has a hard attempt cap and failed
tasks get exponential backoff (30 s, 60 s, 120 s, capped at 300 s) before
re-dispatch. Task ids and owned scopes are unique per attempt; a task is never
duplicated or assigned to overlapping paths. A task with no worktree diff is
recorded as `done` without opening a needless PR. Dependencies, protected
paths and leases still apply.

An existing supervisor started before this feature can be upgraded without
interrupting its workers: run `autofeed` beside it. Both processes use the same
exclusive state lock, so the running supervisor simply picks up newly queued
tasks on its next step.

Restart is safe. Stop with `stop` or Ctrl+C, then run `run` again. Active tasks
are checkpointed as `interrupted`; replay sends them to verification when
evidence exists, requeues them otherwise, or blocks them after `max_attempts`.
A worker that exits between supervisor restarts is also verified from real
evidence, never assumed successful. Worktrees are reused only when they are
still registered on the assigned branch.

## Continue after a blocked task (2026-11-21)

**A missing owner asset is a task blocker, not a stop signal for the project.**
The active GUI OpenCode conversation / a single `opencode run` invocation is
one task and may exit after reporting BLOCKED. Only the separate, running
`canopy_supervisor run` loop can keep launching different workers. A chat
prompt cannot restart a process that has already exited.

This supervisor now has **four independent coding/testing campaigns** after
the original six bounded platform-probe campaigns: bounded shared event
queue, Shell Host failure matrix, registry negative controls, and offline
screenshot provenance checks. They have disjoint file ownership, do not
modify the frozen Classic dock, and require reproducible test evidence.
They are finite, meaningful fallback work; they are not an unlimited task
generator or permission to invent assets. The queue selects the next
eligible task as an earlier campaign becomes BLOCKED or is exhausted.

To resume a previously initialized state from the **supervisor checkout**
(not from the `main` branch where these scripts have not been merged):

```powershell
$state = 'C:\CanopySupervisor\state'
py -3 tools/canopy_supervisor.py --state-root $state check
py -3 tools/canopy_supervisor.py --state-root $state status
py -3 tools/canopy_supervisor.py --state-root $state run
```

`run` stays active and automatically queues tasks until explicitly stopped
or the process is terminated. Run it in a persistent terminal under the
Windows user account with access to Git, GitHub and OpenCode. Keep the PC
awake and avoid starting a second supervisor on the same state root. Use
`status` from a separate terminal to inspect owners and task progress.
Existing exhausted campaigns remain in the ledger. Running `feed` is not
a replacement for `run`.

When all bounded campaigns are done or blocked, the supervisor remains
alive but cannot make further meaningful changes without a new, reviewed
non-overlapping backlog. An idle queue must be reported as **EXHAUSTED**
rather than as "coding" or "autonomous progress." Prefer extending the
roadmap with new concrete coding tasks and acceptance criteria, not
creating more status-only documentation PRs.

Human visual approval and actual Mint guest acceptance remain separate
gates. Never merge to `main` automatically.

## Recover from external-directory evidence rejection (2026-11-21)

The original Windows workers passed tests but were auto-denied when trying
to write their evidence JSON outside the worktree. In a **separate terminal**,
pause and stop the old supervisor before updating its detached checkout:

```powershell
$exe = 'C:\Users\X1\Projects\Canopy-Supervisor\tools\canopy_supervisor.py'
$state = 'C:\CanopySupervisor\state'
py -3 $exe --state-root $state pause
py -3 $exe --state-root $state stop
```

Wait for the original supervisor terminal to return to its PowerShell prompt
and save its logs/checkpoints. DO NOT delete/recreate the state root or
worker worktrees. If the detached supervisor checkout has local edits, do not
switch refs or discard files.

```powershell
Set-Location 'C:\Users\X1\Projects\Canopy-Supervisor'
git status --short
git fetch origin
git switch --detach origin/feat/windows-multi-agent-supervisor-20261121
py -3 -m unittest tests.test_canopy_supervisor -v
py -3 .\tools\canopy_supervisor.py --state-root $state check
```

Only after tests are green, explicitly requeue the three **known** tasks
whose logs show `external_directory` and `auto-rejecting`. This command
requires the queue to be paused, rejects still-live workers or existing PRs,
does not overwrite a validated report, never deletes source edits or
worktrees, and records each reset in the audit history. It is not a general
purpose override of failed work:

```powershell
py -3 .\tools\canopy_supervisor.py --state-root $state retry-evidence-permission `
  --id shared-event-queue `
  --id shell-host-fault-matrix `
  --id registry-negative-controls
py -3 .\tools\canopy_supervisor.py --state-root $state resume
py -3 .\tools\canopy_supervisor.py --state-root $state run
```

The code then retains each worker's existing uncommitted source changes and
starts any retry from its registered worktree. Passing Ubuntu CI tests alone
does not prove actual unattended OpenCode runtime recovery on Windows.
Verify real exit/evidence logs and a draft PR before marking this resolved.

## Recover completed work rejected only for Python test caches (2026-11-21)

Worker branches may start from `main`, which does not necessarily have the
supervisor branch's Python cache ignore rules. The supervisor now ignores only
**untracked** `__pycache__` and `*.py[cod]` data when identifying and
staging changes. Tracked and staged files, including protected assets, remain
visible to the scope gate. Tests set `PYTHONDONTWRITEBYTECODE` where feasible,
but the already-generated local files are not deleted.

If workers exited successfully and `evidence_collected` was recorded, but a
task is `failed` with a **Python cache path** in `last_error`, do not rerun
the agents. Their tests and source code may be reusable. The
`retry-verification` command is deliberately limited to this exact failure,
requires a paused state, matching worktree branch and existing evidence,
rejects live workers and existing PRs, and preserves source files and attempt
counts.

Safely stop the previous supervisor and update the **separate supervisor
checkout** first:

```powershell
$root = 'C:\Users\X1\Projects\Canopy-Supervisor'
$state = 'C:\CanopySupervisor\state'
py -3 "$root\tools\canopy_supervisor.py" --state-root $state pause
py -3 "$root\tools\canopy_supervisor.py" --state-root $state stop
# Wait for the old supervisor terminal to exit before updating.
Set-Location $root
git status --short
git fetch origin
git switch --detach origin/feat/windows-multi-agent-supervisor-20261121
py -3 -m unittest tests.test_canopy_supervisor -v
py -3 .\tools\canopy_supervisor.py --state-root $state check
```

Abort checkout if `git status --short` shows unexpected edits; do not force
reset. Reverify the **three known completed tasks** without a new model call,
while paused:

```powershell
py -3 .\tools\canopy_supervisor.py --state-root $state retry-verification `
    --id shared-event-queue `
    --id shell-host-fault-matrix `
    --id registry-negative-controls
py -3 .\tools\canopy_supervisor.py --state-root $state run --once
py -3 .\tools\canopy_supervisor.py --state-root $state status
```

`REVERIFY_READY 3` is not a success signal. Confirm each task reached
`awaiting_review` with a draft PR and passing CI. Inspect failures before
any further retry. The unrelated `screenshot-provenance-gate` process-loss
task is **not eligible** for this repair.

## Task and evidence contract

Tasks are appended with `add-task`, or edited in `tasks.json` while the
supervisor is stopped. Fields: `id`, `title`, `objective`, `scope`,
`depends_on`, `base`, `branch`, `tests_required`.

The worker writes **`<worktree>/.canopy-worker-evidence.json` only**.
OpenCode's restricted worker cannot write to the supervisor-owned `state/evidence`
directory, even when both locations share a parent path. When the worker exits,
the trusted supervisor checks a 128 KiB bound, rejects symlinks and mismatched
task/branch identities, atomically copies the JSON into
`<state>/evidence/<task-id>/evidence.json`, then removes the temporary
worktree file **before checking the Git diff or opening any PR**. This does
not disable OpenCode permission checks. The JSON format is:

```json
{
  "task_id": "bounded-task",
  "branch": "feat/canopy-supervisor-bounded-task",
  "commit_sha": "PENDING",
  "tests": [
    {"command": "py -3 -m unittest tests.test_x -v",
     "result": "PASS", "output_excerpt": "Ran 1 test ... OK"}
  ],
  "changed_files": ["docs/bounded-task.md"],
  "draft": true,
  "notes": "Actual command output and blockers."
}
```

`commit_sha` is `PENDING` because the supervisor commits after verification.
The supervisor replaces it with the real SHA before creating the draft PR.
`NOT RUN` is accepted only when `tests_required` is false and a reason is given;
a task with no `PASS` test is never published.

## CI and Canopy protections

- No new workflow. Existing required checks still run on the opened draft PR.
- Draft PR bodies state that green CI is not merge authorization, that owner
  visual signoff and real Linux Mint evidence are separate gates, and that the
  established read-only supervisor remains the CI status reporter.
- The supervisor cannot modify the approved Qt GUI design. Those paths are in
  the protected list and are checked twice: at task definition and before
  publish against the real git diff.
- Low-resource rules still apply. The supervisor is event-step driven with a
  bounded poll interval, stores small state, and starts at most three workers.
  It does not add a desktop daemon or a compositor.

## Known limits

- `gh` and `git` must be authenticated on the host; failure is recorded as a
  task-level verification error, never as a successful publish.
- Stall detection uses worker log growth and worktree file changes. A worker
  that thinks silently for longer than `stall_minutes` is interrupted.
- The supervisor is a coordinate-and-publish tool, not a code reviewer, visual
  approver or release manager. Human review stays mandatory.
