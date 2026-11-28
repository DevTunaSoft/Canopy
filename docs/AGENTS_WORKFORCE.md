# Agent workforce and integration policy

## ACTIVE GOAL — Rev3 controlling directive (2026-11-28)

Sole controlling Canopy/LacOS goal: `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md`, SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a` (short `1fba4b1e`). The external supplemental directive and the 2026-11-26/2026-11-27 cap directives described below are `SUPERSEDED_POINT_IN_TIME` for caps, draft-only rules, workforce scheduling and integration authority; retained as history, not retracted or erased. No wallpaper/icon hash protection, named PR hold (#151/#278/#279), security gate or release gate is weakened.

- **A0.1 — finish current work:** let every current Canopy/LacOS assignment finish on its authorized branch and worktree. Do not interrupt, cancel, restart, reassign or change branch merely to apply this directive, an integration priority or a workforce cap. Narrow exceptions only: genuine external blocker, unrecoverable stall, security/safety incident, resource emergency, or demonstrably obsolete/duplicated work. Preserve commits, evidence and pending obligations; checkpoint, never mark complete.
- **Project-scoped cap 8+Hermes:** maximum 8 concurrent Canopy/LacOS subagents plus Hermes; count active project workers, not queued or inactive sessions. Finish valid in-flight assignments naturally if over cap and dispatch no new or replacement project worker until capacity exists. **no-global-change:** other Hermes projects and global agent settings are excluded and must not be modified. This reconciliation PR is DRAFT: no merge, no self-approval.
- **Integration authority / distinct-human-approval blocker:** integration branch and `main` protection require 1 distinct human approving review with `enforce_admins=true`; the only authenticated account (`DevTunaSoft`) authors the eligible PRs, so this is a genuine external blocker. Never self-approve, impersonate a reviewer or bypass protection. Promote eligible PRs to ready, record the exact owner action required, and continue unrelated eligible work.
- **Exclusive guest lease:** use an exclusive guest lease (exclusive session lease with owner, heartbeat and recovery checkpoint) for interactive VM, install/uninstall, display changes, suspend/resume and session restart. Serialize heavy builds, full suites and VM work; never terminate unrelated work to acquire a lock; a timeout is incomplete, not a pass.

Earlier `integration/canopy-classic-20261123` integration wording below is retained as branch history and classified `SUPERSEDED_POINT_IN_TIME`; Rev3 designates `integration/canopy-plasma6-20261127` until the native Plasma baseline gates pass.

Authoritative source (external to this repository): the composer-pasted master
supplemental directive, preserved on disk at
`C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy_master_supplemental_directive_20261126.md`
with SHA-256 `f3ec49fba9317c01354dbd34cf1c5cfedb2625b604f25117c720ae0f44781eae`
(recomputed from on-disk bytes at verification). The bare filename
`canopy_master_supplemental_directive_20261126.md` is **NOT in the tree** at exact
tip `20fb694f2b4a0ea44e2f3032f316ac8c7e65a23a` (`git cat-file -e` fails in this isolated worktree); the same
citation was previously checked and recorded `MISSING` at archived tip
`84684a0f77c81cb0e84d9a679ec57a429dc5c1db` in
`C:/Users/X1/AppData/Local/hermes/cache/scratch/final_git_tree_provenance_84684a0.json`;
no repository blob backs this citation. This file is a concise repository-facing
summary; where wording elsewhere conflicts, the external directive governs. It
does not grant a merge or visual approval.

`SUPERSEDED_POINT_IN_TIME` — Newer owner directive (received after the external source above, 2026-11-26):
the authorized ceiling was **up to 12 concurrent engineering subagents plus
Hermes as lead orchestrator** when productive, independent, non-overlapping
work exists; Rev3 (`1fba4b1e`) now governs with a project-scoped cap 8+Hermes.
This owner directive is newer than the external directive cited
above and supersedes only its 10-agent ceiling; all other requirements and
acceptance gates in that external directive remain in force. It grants no
merge, visual or release approval.

## Workforce

- `SUPERSEDED_POINT_IN_TIME` authorized ceiling (Rev3 cap 8+Hermes governs): **up to 12 concurrent engineering subagents plus Hermes as
  lead orchestrator** under the older owner directive (superseding the earlier
  10-agent ceiling in the external directive above, and all earlier 15-, nine-,
  seven- and four-agent configurations). This is a ceiling, not a quota: assign
  work only when independent, productive, non-overlapping and
  resource-permitting, and do not manufacture assignments to fill slots.
- Indicative initial allocation: 3 core/runtime integration, 2 GUI/usability, 2
  Mint/session/installation, 1 performance/clean code, 1 independent QA,
  1 GitHub/release (10 initially allocated within the 12-agent ceiling);
  redistribute by actual need.
- Isolated worktrees, exact backticked file ownership, disjoint branches and
  dependency-aware assignment remain mandatory. No agent approves its own
  implementation; independent review is required. Throttle heavy builds,
  suites and VM work to keep Hermes and the host responsive.

## PR lifecycle and integration

- DEVELOP → TEST → INDEPENDENT REVIEW → READY → INTEGRATE → VERIFY. Draft PRs
  are temporary working states, not permanent storage.
- Pre-merge: exact head SHA tested, dependencies/ancestry/conflicts checked,
  applicable required checks green, substantive independent review, and any
  owner approval required for the scope. Green CI alone is never authorization.
- Routine independently verified engineering and authorized bounded GUI
  refinements integrate incrementally into
  `integration/canopy-classic-20261123`; record them as **AGENT REVIEWED**,
  never as human approval.
- Post-merge regression is required **after** each merge. There is no circular
  gate requiring post-merge results before the merge that produces them.
- Final visual acceptance, substantial identity changes, high-risk security
  decisions, final release acceptance and any merge to `main` are owner-gated.
  Classic Qt final integration stays draft until real Linux Mint acceptance and
  owner visual approval are recorded. Pending visual acceptance never blocks
  unrelated engineering.
- Named owner holds on **#279**, **#151** and **#278** are preserved. This
  policy reconciliation does not promote, approve, close or merge them.

## Reconciliation scope and residuals

- This change edits only `README.md`, `CONTRIBUTING.md`, `docs/QUALITY.md`,
  `docs/ARCHITECTURE.md`, `.github/PULL_REQUEST_TEMPLATE.md` and this file.
  `AGENTS.md`, `docs/ROADMAP.md`, workflow, test, visual-asset and source paths
  are outside its ownership and were not edited here.
- Historical residual wording in `AGENTS.md` and `docs/ROADMAP.md` ("at least
  four active subagents" floor, 12-agent ceiling) is `SUPERSEDED_POINT_IN_TIME`
  as of Rev3 (`1fba4b1e`); both files are reconciled in the same Rev3 change.
  No cited source is retracted or erased.
- No new visual, security or release approval is claimed by this documentation
  change.
