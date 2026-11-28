# Agent workforce and integration policy

Authoritative source (external to this repository): the composer-pasted master
supplemental directive, preserved on disk at
`private-evidence/scratch/canopy_master_supplemental_directive_20261126.md`
with SHA-256 `f3ec49fba9317c01354dbd34cf1c5cfedb2625b604f25117c720ae0f44781eae`
(recomputed from on-disk bytes at verification). The bare filename
`canopy_master_supplemental_directive_20261126.md` is **NOT in the tree** at exact
tip `20fb694f2b4a0ea44e2f3032f316ac8c7e65a23a` (`git cat-file -e` fails in this isolated worktree); the same
citation was previously checked and recorded `MISSING` at archived tip
`84684a0f77c81cb0e84d9a679ec57a429dc5c1db` in
`private-evidence/scratch/final_git_tree_provenance_84684a0.json`;
no repository blob backs this citation. This file is a concise repository-facing
summary; where wording elsewhere conflicts, the external directive governs. It
does not grant a merge or visual approval.

Newest owner amendment (2026-11-26 master directive, SHA-256 `f240bcdf635a498a7476c8104cbf3dc4e6cda492abba318254d80fce7566a197`)
the authorized ceiling is **8 concurrent engineering subagents plus Hermes as
lead orchestrator (9 total)** when productive, independent, non-overlapping
work exists. Transition is non-disruptive: healthy workers finish their current
assignments and no replacement is spawned above 8. The 15+Hermes (PR #711) and
11+Hermes authorizations are SUPERSEDED_POINT_IN_TIME, not silently erased; their
evidence remains historical. The authoritative external amendment is
`private-evidence/downloads/CANOPY_MASTER_DIRECTIVE.md`, SHA-256 `f240bcdf635a498a7476c8104cbf3dc4e6cda492abba318254d80fce7566a197`.
All other requirements and acceptance gates in the cited external directive
remain in force. It grants no merge, visual or release approval.

## Workforce

- Authorized ceiling: **8 concurrent engineering subagents plus Hermes as lead
  orchestrator (9 total)** under the 2026-11-26 master directive amendment
  (superseding all earlier workforce ceilings, including 15, 12 and 10). This is
  a ceiling, not a quota: assign work only when independent, productive,
  non-overlapping and resource-permitting, and do not manufacture assignments
  to fill slots. Do not interrupt healthy workers during the transition down to
  8, and do not refill above it.
- Indicative allocation: 4 product engineering (shared core; native Mint/session;
  Qt compilation/runtime; desktop; dock; launcher; windows/workspaces;
  Files/notifications/settings; performance), 2 independent QA, and 2
  integration/release; redistribute by actual need.
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

- Historical scope of the earlier reconciliation (DOC-119 lineage): that change
  edited only `README.md`, `CONTRIBUTING.md`, `docs/QUALITY.md`,
  `docs/ARCHITECTURE.md`, `.github/PULL_REQUEST_TEMPLATE.md` and this file;
  `AGENTS.md` and `docs/ROADMAP.md` were then outside its ownership. ND-050
  supersedes that scope and does edit `AGENTS.md`, `docs/ROADMAP.md` and the
  listed docs/config paths; no workflow, test, visual-asset or compiled source
  path is edited by ND-050.
- Workforce ceiling reconciliation: the earlier pre-amendment minimum-worker floor and agent ceiling in
  `AGENTS.md` and `docs/ROADMAP.md` were reconciled in this change to
  8 subagents plus Hermes (9 total). `docs/ARCHITECTURE.md` and
  `docs/QUALITY.md`, which the superseded PR #711 left stale, are corrected here
  too. No workforce authorization is claimed beyond the cited owner amendment.
- No new visual, security or release approval is claimed by this documentation
  change.
