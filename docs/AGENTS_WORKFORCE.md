# Agent workforce and integration policy

Authoritative source (external to this repository): the composer-pasted master
supplemental directive, preserved on disk at
`C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy_master_supplemental_directive_20261126.md`
with SHA-256 `f3ec49fba9317c01354dbd34cf1c5cfedb2625b604f25117c720ae0f44781eae`
(recomputed from on-disk bytes at verification). The bare filename
`canopy_master_supplemental_directive_20261126.md` is **NOT in the tree** at exact
tip `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` (`git cat-file -e` fails) and is
recorded `MISSING` in
`C:/Users/X1/AppData/Local/hermes/cache/scratch/final_git_tree_provenance_84684a0.json`;
no repository blob backs this citation. This file is a concise repository-facing
summary; where wording elsewhere conflicts, the external directive governs. It
does not grant a merge or visual approval.

## Workforce

- Authorized ceiling: **10 concurrent engineering subagents plus Hermes as
  lead orchestrator**. This supersedes all earlier 15-, nine-, seven- and
  four-agent configurations. Ten is a ceiling, not a quota: assign work only
  when independent, productive and resource-permitting, and do not manufacture
  assignments to fill slots.
- Indicative allocation: 3 core/runtime integration, 2 GUI/usability, 2
  Mint/session/installation, 1 performance/clean code, 1 independent QA,
  1 GitHub/release; redistribute by actual need.
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
- Known residual wording outside this scope: `AGENTS.md` and `docs/ROADMAP.md`
  still contain a "at least four active subagents" floor alongside the 10-agent
  ceiling in `docs/ROADMAP.md`. Their owners must reconcile that text; this
  file and the cited directive are authoritative until then.
- No new visual, security or release approval is claimed by this documentation
  change.
