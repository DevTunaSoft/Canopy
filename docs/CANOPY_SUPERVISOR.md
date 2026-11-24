# Canopy multi-agent supervisor (bounded pilot)

**Status: implementation under verification.** A passing unit test is not proof
that workers ran, recovered, or produced a real draft PR. See
[verification evidence](SUPERVISOR_VERIFICATION.md) for exact commands and
results. This document supplements, and does not replace, `AGENTS.md`,
`README.md`, `docs/ARCHITECTURE.md`, `docs/QUALITY.md` and the coordination
ledger proposed in PR #133.

## Recommended: one-click Windows Autopilot (no recurring PowerShell)

The repository now includes `tools/Enable-Canopy-Autopilot.cmd`.
**Download it and double-click once** under the existing Windows user
account. It uses standard Git and the existing Python launcher to prepare
a **separate clean checkout** under
`%LOCALAPPDATA%\\CanopyAutopilot\\supervisor`. It does not overwrite
`C:\\Users\\X1\\Projects\\Canopy`, the previous supervisor checkout,
the task ledger or anyone's feature worktree.

The one-time installer copies a stable `Canopy-Watchdog.pyw` into the
per-user application directory and registers a single Task Scheduler entry
named `Canopy-Autopilot-<12-digit-hash>`:

- Every five minutes, Windows launches the watchdog under the **current
  user's limited permissions**. It starts immediately following installation.
- It refuses to compete with an already active supervisor or watchdog. When
  idle, it safely updates only its clean isolated checkout, appends any
  missing 100-backlog jobs idempotently and calls the existing supervisor.
- The supervisor retains the three-agent cap, task retries and watchdog
  timeout; draft PRs still require independent review. The launched Python
  process does not need the original PowerShell console to remain open.
- Exceptions are recorded in
  `C:\\CanopySupervisor\\state\\autopilot-status.json` and
  `autopilot-history.jsonl`. It reports the actual 100-task counts rather
  than treating idle workers as completed engineering.
- An explicit pause is honored; the installer unpauses only once when the
  operator chooses to enable it. A network outage can reuse the current
  checkout but can block new remote refs, so the next scheduled attempt
  retries. Missing OpenCode credentials, free-model quota, unavailable Mint
  VM, failed CI and required human visual approval remain real blockers,
  not success.
- The task has **no admin privilege**, does not require a password,
  does not merge PRs, does not touch approved art and does not disable
  operating-system defenses.
- The monitor runs while Windows is running with the user's session and
  Task Scheduler available; it is not a cloud agent and does not execute
  while the PC is powered off.
- Uninstall through
  `py -3 tools/canopy_autopilot.py uninstall --settings
  %LOCALAPPDATA%\\CanopyAutopilot\\autopilot.json`.
  Uninstall removes only the owned scheduled task and settings, preserving
  work history. This command is documented for support, not required for
  routine operation.

This remains a Windows-specific integration. Unit tests/CI can validate the
scheduler invocation and recovery logic, but cannot assert that Task
Scheduler registration succeeded on the user's real PC until the one-click
installer actually runs there. On setup failure it opens the local setup log
in Notepad, with no copy/paste troubleshooting required.

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

## One-paste bounded Qt development wave (November 21, 2026)

This is the next autonomous work batch, not a perpetual task generator.
Four previous coding assignments already have draft PRs #152-#155.
Do not requeue them. The genuine Qt Classic app resides in draft PR #151:
main does not contain that prototype. All three new tasks have nonoverlapping
owned paths and target the Qt draft branch as their stacked PR base, not main.

The tasks cover Linux Mint guest runtime acceptance, safe user-level preview
packaging, and compiled-Qt interaction smoke testing. These are support toward
completion, not evidence that a Mint VM, approved landscape wallpaper or the
entire shell has been accepted.

One-time operator step: press Ctrl+C in the old continually running supervisor
window and ensure it has exited. Do not interrupt active workers. From a new
Windows PowerShell window, paste the following block exactly once:

~~~powershell
$ErrorActionPreference = 'Stop'
$w = 'C:\Users\X1\Projects\Canopy-Supervisor'
$state = 'C:\CanopySupervisor\state'
py -3 "$w\tools\canopy_supervisor.py" --state-root $state pause
if ($LASTEXITCODE -ne 0) { throw 'Pause failed' }
if ((git -C $w status --porcelain)) { throw 'Supervisor checkout has edits; preserve them before updating' }
git -C $w fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
git -C $w switch --detach origin/feat/windows-multi-agent-supervisor-20261121
if ($LASTEXITCODE -ne 0) { throw 'Supervisor update failed' }
Push-Location $w
try {
    py -3 -m unittest tests.test_canopy_supervisor tests.test_canopy_next_wave -q
    if ($LASTEXITCODE -ne 0) { throw 'Local supervisor tests failed' }
    py -3 .\tools\canopy_next_wave.py --state-root $state --start
    if ($LASTEXITCODE -ne 0) { throw 'Qt wave stopped with a blocker; review dashboard' }
} finally {
    Pop-Location
}
~~~

The wave tool atomically appends the new assignments to the existing roadmap,
under the state lock. It never resets the task ledger or worktrees, regenerates
approved assets, duplicates old PRs, or merges anything. It verifies the Qt
branch from GitHub and preserves the configured free OpenCode model.
Re-running setup does not duplicate tasks. The worker loop stops itself when
the assigned roadmap is exhausted, prints QT_WAVE_FINISHED, and reports
failure separately. Keep the PC on during the run; this is a local continuous
process, not a cloud or background scheduled service. Work on other projects
in separate terminals or applications.

A new single-runner lock prevents overlapping modern supervisor loops, but
the older supervisor predates that protection: close it first.

## 100-task autonomous engineering backlog (2026-11-21)

The owner has approved **100 planned engineering assignments**, but only
**three** simultaneous OpenCode Go free-model workers. The backlog covers
launcher, dock integration models, app launching, window management, Linux
Mint guest tooling, installer safety, reliability, security, performance and
accessibility (10 tasks in each category). The jobs are independently scoped,
bounded, reproducible and targeted to the compiled Qt Classic prototype
feature branch. They **do not** modify approved artwork, frozen dock layout,
wallpaper, QML/C++, OS settings or existing protected files. A completed
modular job does NOT mean its live Qt integration or the entire shell is
complete; reviews and integration remain separate gates.

The catalog source of truth is tools/canopy_backlog_100.py. The script
validates exactly 100 unique task IDs and 200 owned file paths before changing
state. It **appends** new jobs to the current optional roadmap.json without
resetting the ledger, deleting drafts or rewriting old work. A normal state
with the previous three Qt wave entries becomes a 103-entry roadmap; the new
explicit safety cap is 128. Run twice safely: the second run adds zero tasks.
No task is allowed to merge or claim approval from green tests alone.

**Recovery and no silent stalls:** worker logs and worktree file changes form
progress signatures. Inactivity longer than stall_minutes (default six) or
absolute elapsed runtime longer than task_timeout_minutes (default 45)
interrupts the worker, even if it is still writing logs. Saved checkpoints
allow at most max_attempts (default two) with exponential cooldown; then
the worker becomes BLOCKED and independent assignments continue. Missing
remote base branches receive at most two preflight retries, checkpointed to
disk. Impossible queued dependencies are quarantined. Dashboard shows
roadmap planned, pending and active counts. An incomplete wave is explicitly
reported as INCOMPLETE, never FINISHED green. This prevents **silent infinite
waiting**, not all external failures: network outages, free-model quota,
computer shutdown, and legitimate missing Mint/visual approval still require
resolution. If PowerShell closes, it does NOT continue invisibly or survive
reboot; relaunch from checkpoint after verifying no workers are active.

**To start on Windows** when the prior supervisor loop is stopped and zero
workers are active, run these commands in a single PowerShell window:

~~~powershell
$ErrorActionPreference = 'Stop'
$w = 'C:\Users\X1\Projects\Canopy-Supervisor'
$s = 'C:\CanopySupervisor\state'
py -3 "$w\tools\canopy_supervisor.py" --state-root $s pause
if ($LASTEXITCODE -ne 0) { throw 'Could not pause' }
if (git -C $w status --porcelain) { throw 'Local supervisor changes exist; do not overwrite' }
git -C $w fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $w switch --detach origin/feat/windows-multi-agent-supervisor-20261121
if ($LASTEXITCODE -ne 0) { throw 'Update failed' }
Push-Location $w
try {
    py -3 -m unittest tests.test_canopy_backlog_100 tests.test_canopy_supervisor -q > "$s\backlog-100-preflight.log" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Get-Content "$s\backlog-100-preflight.log" -Tail 60
        throw 'Supervisor safety tests failed'
    }
    py -3 .\tools\canopy_backlog_100.py --state-root $s --start
    if ($LASTEXITCODE -ne 0) { throw 'Backlog finished with blockers or incomplete work; review dashboard' }
} finally {
    Pop-Location
}
~~~

Minimize the PowerShell window and keep the PC on. Do not start the same
supervisor in another process; the lifetime runner.lock prevents competing
new runners. To inspect progress in a separate brief terminal, use
canopy_supervisor.py status, or read C:\CanopySupervisor\state\dashboard.md.
No automatic merges or unattended changes to Windows startup are performed.

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

Verification evidence must contain a lowercase hex `commit_sha` of 7-40
characters, as required by `policy.COMMIT_SHA`; `PENDING` is rejected
fail-closed before publication. No runtime SHA substitution occurs.
`NOT RUN` is permitted by current validation; only the `PASS` + draft
requirement is enforced. A task with no `PASS` test is never published.

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
