# Recovery evidence follow-up — supervisor verification

**Recorded 2026-11-21 (UTC).** This document transcribes the exact launch,
failure-recovery and draft-PR evidence from `docs/SUPERVISOR_VERIFICATION.md`.
It is a bounded supervisor-pilot record only. It is **not** Canopy release
approval, Linux Mint acceptance, owner visual signoff, or permission to merge
anything to `main`. This task created no PR and merged or published nothing.

Source of truth: [`docs/SUPERVISOR_VERIFICATION.md`](SUPERVISOR_VERIFICATION.md).

## Environment (as recorded by the source)

- Host: Windows 11, PowerShell, Python 3.14 (`py -3`), Git for Windows.
- OpenCode CLI 1.19.6, `opencode-go` provider, worker model
  `opencode-go/hy4-flash-free`.
- GitHub CLI 2.104.0, authenticated as `DevTunaSoft` with `repo` scope.
- Private disposable repository: `DevTunaSoft/canopy-supervisor-verification`,
  seeded with `README.md` and `tests/test_smoke.py` at `e020b35`.
- Canopy branch under test: `feat/windows-multi-agent-supervisor-20261121`.

A private throwaway repository was used so verification PRs would not add noise
to the Canopy stacked-PR queue. No Canopy Qt, artwork or CI file was changed.

## Launch evidence

Commands (state root outside the working tree), verbatim from the source:

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

1. Three independent workers launched at **21:27:56–21:27:57 UTC** with
   distinct PIDs (21780, 14356, 30064), workers (`worker-1..3`), worktrees
   (`state/worktrees/task-{a,b,c}`) and branches
   (`feat/canopy-supervisor-task-{a,b,c}`). Concurrency limit 3 was enforced.
2. Each worker created only its owned file (`docs/task-a.md`, `docs/task-b.md`,
   `docs/task-c.md`) and ran the real command
   `py -3 -m unittest tests.test_smoke -v`, which reported
   `Ran 1 test ... OK` in the captured log. Each wrote evidence JSON with
   `draft: true`.

## Failure-recovery evidence

1. At **21:28:38 UTC**, task-a's worker process was killed with
   `taskkill /PID 21780 /T /F` to simulate an interrupted task.
2. The supervisor logged `recovered` with the message
   `worker process lost or lease expired; task recovered`, then relaunched
   task-a on `worker-1` with **PID 30712** and **attempt 2**.
3. The task-a checkpoint changed from `launched` to `recovered`.
4. Clean `stop`, restart and checkpoint replay were exercised. Interrupted
   tasks with evidence were replayed to verification; those without evidence
   were requeued. A limited retry budget was raised from **2 to 3** in the
   verification state because the injected kill consumed one attempt.
5. Verification rejected an out-of-scope `__pycache__` byproduct in task-a
   before commit. After cleanup, all three tasks reached `awaiting_review`.

Automated checks recorded alongside the live run (from the source, not re-run
by this task): supervisor unit tests PASS — 42 tests; Windows-applicable
regression suite PASS — 221 tests; byte compile PASS; full discovery on Windows
PASS — 282 tests with 53 POSIX-only skips; Canopy draft PR #135 `foundation`
check PASS (25 s, Ubuntu, commit `250257d`) and `desktop-menu` check PASS
(12 s, Ubuntu, commit `250257d`).

## Draft-PR evidence

| PR | Branch | Files changed | Draft |
| --- | --- | --- | --- |
| [#1](https://github.com/DevTunaSoft/canopy-supervisor-verification/pull/1) | `feat/canopy-supervisor-task-a` | `docs/task-a.md` | yes |
| [#2](https://github.com/DevTunaSoft/canopy-supervisor-verification/pull/2) | `feat/canopy-supervisor-task-b` | `docs/task-b.md` | yes |
| [#3](https://github.com/DevTunaSoft/canopy-supervisor-verification/pull/3) | `feat/canopy-supervisor-task-c` | `docs/task-c.md` | yes |

Verification command from the source:

```
gh pr view <n> --repo DevTunaSoft/canopy-supervisor-verification --json isDraft,headRefName,baseRefName,files,url
```

All target `main`, all are drafts, and the file sets are disjoint. No PR was
merged; the supervisor code contains no merge operation.

The implementation draft PR is
[#135](https://github.com/DevTunaSoft/Canopy/pull/135). The source also records
three later worker PRs awaiting review: #136 (`qt-mint-evidence`,
`feat/canopy-supervisor-qt-mint-evidence`), #137 (`visual-qa-evidence`,
`feat/canopy-supervisor-visual-qa-evidence`) and #138
(`regression-security-notes`, `feat/canopy-supervisor-regression-security-notes`),
each with a `foundation PASS` check and no worker restart.

## What this does not prove

No claim is made about Linux Mint guest acceptance, real Qt screenshots, owner
visual approval, low-resource targets, Shell Pack runtime loading, or safety of
any community package. Those gates remain documented in
[`docs/QUALITY.md`](QUALITY.md) and
[`docs/RELIABILITY_99_GATE_AUDIT.md`](RELIABILITY_99_GATE_AUDIT.md). Green CI or
a draft PR is not merge authorization. Qt build, Qt screenshots and Linux Mint
guest acceptance remain blocked or not run as documented in the worker PRs;
they are not claimed as passed.
