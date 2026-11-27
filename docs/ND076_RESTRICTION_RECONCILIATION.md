# ND-076 — restriction reconciliation at exact integration tip `ec910d7`

Exact base tip: `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(tree `3c6110a77e9e34be367a4d11b29c3d6a13138bab`). Base branch:
`integration/canopy-classic-20261123`. Main remains
`65a9e0de107355e04f91356db7358debf751760a`. Governing owner directive:
`C:/Users/X1/Downloads/CANOPY_MASTER_DIRECTIVE.md`, SHA-256
`f240bcdf635a498a7476c8104cbf3dc4e6cda492abba318254d80fce7566a197`
(amendment 2026-11-26). This is documentation/evidence only: no source,
visual asset, workflow, enforcing test, PR, approval, merge, build or release
action is part of this reconciliation.

## 1. Current owner-controlled gate language

- Workforce ceiling: **8 concurrent engineering subagents plus Hermes as lead
  orchestrator (9 total)**, a ceiling and not a quota. Earlier 15-, 11-, 12-,
  10-agent and four-worker floors are `SUPERSEDED_POINT_IN_TIME`; byte backups
  and git history are preserved and nothing is erased or retracted here.
- GUI ownership: Hermes has owner-granted engineering authority for GUI/QML,
  visual design, artwork processing and visual QA under the 2026-11-25 and
  2026-11-26 directives. The ChatGPT-exclusive visual ownership rule is
  `SUPERSEDED_POINT_IN_TIME`.
- Final owner gates remain binding: approved icons, alpine-lake wallpaper, dock
  geometry, colours, typography and frozen pins are byte-preserved; final
  visual acceptance, substantial identity changes, high-risk security
  decisions, release and any `main` merge are owner-only. Current visual
  status token: `AWAITING_OWNER_VISUAL_APPROVAL`.
- Compiled work: compiled/QML/C++ host wiring is permitted engineering; a
  blanket compiled-path ban is a superseded restriction. A compiled-path
  deny-list hit is an integration safety stop or scope finding, never an owner
  decision, never an approval and never a substitute for real Mint evidence.
- Named holds on #279, #151 and #278 are preserved. This change does not
  promote, approve, comment on, close or merge them.

## 2. Reconciliation ledger

All classifications use `retracted=false`, `erased=false` and
`file_modified_by_this_pass=false` unless the row states otherwise. Historical
claims survive in git and in the cited on-disk evidence.

| ID | Prior claim / location at `ec910d7` | Classification now | Current wording or disposition |
|---|---|---|---|
| R1 | `README.md`, `CONTRIBUTING.md`, `docs/QUALITY.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `docs/AGENTS_WORKFORCE.md` named a 12+Hermes or 10-agent ceiling | `SUPERSEDED_POINT_IN_TIME`, superseded by directive `f240bcdc…` | 8 subagents + Hermes, with the older numbers retained as historical text |
| R2 | `README.md` described the earlier 15/9/7/4 configurations; `docs/AGENTS_WORKFORCE.md` described 15-, nine-, seven-, four-agent and ten-agent allocations | `SUPERSEDED_POINT_IN_TIME` | Historical configurations retained; current starting allocation 4 product / 2 QA / 2 integration-release |
| R3 | `AGENTS.md` line 13 and line 88 contain "at least four" active subagent floors | `SUPERSEDED_POINT_IN_TIME`; **not edited** — the guarded write to this protected instruction file was refused, and no alternate route was attempted | Stale floors remain byte-identical at `ec910d7`; the controlling docs above and directive `f240bcdc…` govern. Owner-side correction is a separate authorized action. |
| R4 | Integration ledgers used "compiled-path deny-list" language as if compiled paths were categorically barred | `SUPERSEDED_POINT_IN_TIME` as a restriction claim; the deny-list itself is retained as a real safety gate | Compiled engineering permitted; approved visual/geometry paths still owner-gated; deny-list hits are safety/scope states, not consent |
| R5 | `docs/CLASSIC_OWNER_ICONS_OPTIN.md` status line `AWAITING_CHATGPT_VISUAL_APPROVAL` | Literal token retained (`SUPERSEDED_POINT_IN_TIME`), not erased | Added explicit reconciliation note; current status `AWAITING_OWNER_VISUAL_APPROVAL` |
| R6 | `docs/WALLPAPER_CHANGE_PATH_CONTRACT.md` quoted a scoped checker run reporting `AWAITING_CHATGPT_VISUAL_APPROVAL problems=0` | Scoped historical run output; token `SUPERSEDED_POINT_IN_TIME` | Retained verbatim with a clarifying note; no claim that this run is a live-tip approval |
| R7 | `tools/check_visual_lock.py` and `tests/test_check_visual_lock.py` enforce the legacy token; `tests/test_classic_default_owner_icons_optin_128c973.py` asserts the token in the icons doc | `UP_TO_DATE` as frozen enforcement/evidence | Not edited. Removing the token there would break real approval enforcement; the reconciliation is prose-only around those strings. |
| R8 | Protected PR #279 (`ci/visual-lock-gate-20261123`, head `17bb473e9b9740481f0269440391ab92e528139d`) edits `.github/workflows/foundation.yml` and `tests/test_check_visual_lock.py` | `PRESERVED`, no PR or file mutation | Its owner gate and body language are untouched; this PR does not edit workflows, tests, visual assets or source. |

## 3. Scope proof

Changed paths are documentation only: `README.md`, `CONTRIBUTING.md`, `AGENTS.md`
is **not** changed, `docs/AGENTS_WORKFORCE.md`, `docs/QUALITY.md`,
`docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `.github/PULL_REQUEST_TEMPLATE.md`,
`docs/CLASSIC_OWNER_ICONS_OPTIN.md`,
`docs/WALLPAPER_CHANGE_PATH_CONTRACT.md`, and this new file. No QML, C++,
CMake, asset, icon, wallpaper, workflow, enforcing test, PR body, issue, branch
or main-tree path is in scope. No compile, Mint guest, VM, approval, promotion
or merge was performed.

## 4. Evidence boundaries

- Directive SHA-256 was recomputed from the on-disk owner directive bytes.
- Exact base tip/tree were read from local git objects and the live integration
  ref was re-queried with `git ls-remote` before publication.
- No owner decision is made or cleared: C06-C13 and D1-D4 from the exact-tip
  owner decision packet remain open/owner-gated. In particular
  `release_ready=false` and `NO-GO` carry forward unchanged.
- CI captures, byte identity and scoped renders are not owner visual approval.

## 5. Verification

Run in the isolated worktree pinned to `ec910d7` with `PYTHONPATH` set to the
worktree root (host Windows 11, Python 3.14.9):

- `python tools/check_foundation.py` → rc=0,
  `PASS: foundation files, tagline, and local Markdown links`. Final log
  SHA-256 `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad`
  (`C:/Users/X1/AppData/Local/hermes/cache/scratch/nd076_verify_final/foundation.log`).
- `python -m unittest tests.test_foundation tests.test_foundation_link_scope_guard tests.test_classic_source tests.test_classic_default_owner_icons_optin_128c973 tests.test_check_visual_lock tests.test_pe100_wallpaper_change_path` →
  rc=0, `Ran 69 tests`, `OK`, zero FAIL/ERROR. Final log SHA-256
  `3ee95d2e83d353b6b50fa7205a4078985cb93e1fd727025e0593066c65252c8b`
  (`C:/Users/X1/AppData/Local/hermes/cache/scratch/nd076_verify_final/docs_tests.log`).
- Not run here: full suite, Qt compile, Mint guest and any real desktop
  measurement (`NOT_RUN`). Those gates remain owner/engineering blockers and
  are not implied by this docs-only pass.
