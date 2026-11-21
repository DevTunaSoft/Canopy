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
| Supervisor unit tests | PASS — 42 tests | `py -3 -m unittest tests.test_canopy_supervisor -q` |
| Regression suite (Windows-applicable modules) | PASS — 221 tests | `py -3 -m unittest -q <all tests except three POSIX-only modules>` |
| Byte compile | PASS | `py -3 -m compileall -q canopy_supervisor tools/canopy_supervisor.py tests/test_canopy_supervisor.py` |
| Full discovery on Windows | BLOCKED — pre-existing failures | `py -3 -m unittest discover -s tests -q` |
| Canopy draft PR #135 `foundation` check | PASS — 16 s, Ubuntu, commit `bbd9c40` | `gh pr checks 135 --repo DevTunaSoft/Canopy` |

The full Windows run reports errors in `test_classic_preview_menu` because it
patches `os.geteuid`, which does not exist on Windows, and in
`test_mint_classic_qt_smoke` / `test_mint_acceptance_report_gate` because they
assume POSIX executable bits. Those modules are untouched by this branch. CI on
Ubuntu (`foundation.yml` runs `unittest discover`) is the authoritative place
for them. No CI workflow was added or duplicated by this change.

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

## What this does not prove

The implementation draft PR is
[#135](https://github.com/DevTunaSoft/Canopy/pull/135). No claim is made about
Linux Mint guest acceptance, real Qt screenshots, owner visual approval,
low-resource targets, Shell Pack runtime loading, or safety of any community
package. Those gates remain documented in `docs/QUALITY.md` and
`docs/RELIABILITY_99_GATE_AUDIT.md`. Green CI or a draft PR is not merge
authorization.
