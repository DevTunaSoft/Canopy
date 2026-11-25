# Continuous Canopy worker — controlled Windows setup (proposal)

This is an **operator runbook**, not a deployed background agent. No unattended worker is running merely because this file exists.

## Scope and trust
- Primary implementation: Claude Code on a dedicated Windows workstation with Git and a working repository checkout.
- Secondary reviewer: GitHub Copilot, **review only**. GitHub Actions independently runs available CI checks.
- The owner retains visual signoff; do not overwrite the approved eight icons, dock geometry, or artwork.
- Read `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/QUALITY.md`, and `CANOPY_PROJECT_STATE.md` (once #133 merges). The project-state file supplements existing contracts.
- One lead worker initially. Additional workers require distinct Git worktrees, separate branch ownership and a coordination lock to prevent duplicate edits.
- Never auto-merge to main, disable security controls, expose secrets, or treat a passing CI job as real Mint or visual acceptance.

## First supervised session (PowerShell)
Run from a trusted, existing checkout. Confirm the executable and account are ready before any unattended scheduling.

```powershell
Set-Location 'C:\path\to\Canopy'
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
claude --version
gh auth status
claude
```

Inside Claude Code, use this initial task:

> Read the complete Canopy engineering contract and current issue #132. Inspect current main and all relevant open PRs before editing. Work only on a new feature branch or dedicated worktree. First resolve the Qt integration ancestry/conflicts, preserve owner-approved visuals, and run real Qt build/smoke checks. Produce an evidence-based draft PR with exact SHA, command output, screenshots where available, and explicit Mint/visual blockers. Never merge to main or change approved artwork without review. If blocked, record the blocker and stop instead of inventing success.

## Continuous supervisor requirements — build before unattended use
A production worker supervisor must:
1. Acquire an exclusive local lock; never spawn duplicate workers after reboot.
2. Fetch a single queued, unclaimed GitHub issue; atomically record owner/branch and lease expiry. Handle stale claims.
3. Run the coding process with a bounded task and hard time limit, plus heartbeat, structured stdout/stderr logs and redaction.
4. Enforce one task per worktree, maximum retries, backoff, and pause on authentication, quota, destructive operation, or unresolved conflicts.
5. Check exit status, verify committed SHA and CI conclusions, and keep failing or incomplete PRs in draft.
6. Save checkpoint to GitHub before moving to another task. Distinguish NOT RUN from PASS.
7. Require human signoff for visuals and real Mint evidence. Never run `git push --force` or merge automatically.
8. Provide an operator pause/stop control, log retention and safe restart after Windows update or power loss.
9. Verify Claude Code's actual noninteractive invocation and permission policy on the installed version **before** building scheduled execution; don't assume interactive prompts can be safely bypassed.

**Not yet implemented:** Windows service/Task Scheduler registration, supervisor, issue leasing, worktree locks, retries, watchdog, or background worker. No continuous-operation claim is authorized.

## Release integration priority
[#132](https://github.com/DevTunaSoft/Canopy/issues/132) is the current integration blocker. Qt PR ancestry is stacked (#100 → #119 → #120 → #121 → #123 → #124); #102 and #109 branch from #100; #118 is separate. Review exact head SHA and CI before rebase/cherry-pick. CI on #100 and #124 passed for their checked heads on 2026-11-21, but neither proves real Linux Mint acceptance.
