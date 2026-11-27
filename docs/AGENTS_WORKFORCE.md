# Agent workforce and integration policy

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

Governing owner directive (latest, received after the external source above, 2026-11-26):
`C:/Users/X1/Downloads/CANOPY_MASTER_DIRECTIVE.md`, SHA-256
`f240bcdf635a498a7476c8104cbf3dc4e6cda492abba318254d80fce7566a197`. It amends
the owner-authorized ceiling to **8 concurrent engineering subagents plus Hermes
as lead orchestrator (9 total)**. The 15-, 11-, 12- and 10-agent configurations
and the old four-worker floor are `SUPERSEDED_POINT_IN_TIME`: byte backups are
preserved and nothing here erases them. The external f3ec49f… directive's
non-workforce security, architectural, visual and acceptance requirements remain
in force. This directive grants no merge, release or final visual approval.

## Workforce

- Authorized ceiling: **8 concurrent engineering subagents plus Hermes as
  lead orchestrator (9 total)** under the governing owner directive
  `f240bcdf…` (superseding the earlier 15-, 11-, 12- and 10-agent
  configurations and the four-worker floor, all `SUPERSEDED_POINT_IN_TIME`).
  This is a ceiling, not a quota: assign work only when independent, productive,
  non-overlapping and resource-permitting, and do not manufacture assignments
  to fill slots.
- Starting allocation: 4 product engineering, 2 independent QA, 2
  integration/release; redistribute by actual need. The earlier 3/2/2/1/1/1
  ten-agent allocation is `SUPERSEDED_POINT_IN_TIME`.
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
  Current visual status is `AWAITING_OWNER_VISUAL_APPROVAL`. Hermes has owner
  authority for GUI/visual engineering under the 2026-11-25 and 2026-11-26
  directives; the ChatGPT-exclusive visual ownership rule is
  `SUPERSEDED_POINT_IN_TIME`. Compiled QML/C++/host work is not categorically
  forbidden, but approved artwork, wallpaper, dock geometry, colours,
  typography and frozen pin paths remain byte-frozen and owner-gated. A
  compiled-path deny-list hit or CI capture is a safety/evidence state, never
  owner consent. Classic Qt final integration stays draft until real Linux Mint
  acceptance and owner visual approval are recorded. Pending visual acceptance
  never blocks unrelated engineering.
- Named owner holds on **#279**, **#151** and **#278** are preserved. This
  policy reconciliation does not promote, approve, close or merge them.

## Reconciliation scope and residuals

- This reconciliation edits `README.md`, `CONTRIBUTING.md`, `docs/QUALITY.md`,
  `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `.github/PULL_REQUEST_TEMPLATE.md`, two scoped evidence docs, adds the ND-076
  reconciliation doc and this file. Workflow, test, visual-asset, source,
  `AGENTS.md` and protected-PR paths were not edited.
- `AGENTS.md` retains its two "at least four active subagents" sentences: the
  guarded write to that protected instruction file was refused
  (`RETRACTED=false`, `ERASED=false`, `FILE_MODIFIED_BY_THIS_PASS=false`). Both
  sentences are `SUPERSEDED_POINT_IN_TIME` against directive `f240bcdc…` and are
  catalogued in [ND-076 reconciliation](ND076_RESTRICTION_RECONCILIATION.md);
  no attempt to route around the guard was made.
- No new visual, security, release or merge approval is claimed by this
  documentation change; protected PR #279 is untouched.
