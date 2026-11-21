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

`roadmap.json` in the state root holds the approved, bounded follow-up tasks.
If absent, a small built-in catalog of Canopy evidence tasks is used. Each step
refills the pipeline to `max_workers` non-terminal tasks, so when one worker
finishes, the next approved task is queued without a human prompt. Task ids and
owned scopes are unique; a task is never duplicated or assigned to overlapping
paths. Dependencies, protected paths, leases and attempt limits still apply.

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

## Task and evidence contract

Tasks are appended with `add-task`, or edited in `tasks.json` while the
supervisor is stopped. Fields: `id`, `title`, `objective`, `scope`,
`depends_on`, `base`, `branch`, `tests_required`.

The worker writes `<state>/evidence/<task-id>/evidence.json`:

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
