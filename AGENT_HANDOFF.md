# Agent Handoff

## Rules for continuing agents

- Read `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/QUALITY.md`,
  and this file before editing.
- Work on feature branches; never merge to `main`.
- Do not modify approved dock geometry, exact PNG icons, wallpaper, or Qt GUI
  without owner approval.
- Do not generate replacement artwork.
- Do not create documentation-only PRs.
- Keep PRs draft until CI, tests, and visual approval requirements are met.
- Run available tests and record exact commands and output.
- Push verified work to GitHub.
- Preserve existing engineering requirements and low-resource targets.

## Current ownership

- PR #135: supervisor implementation and tests.
- PR #151: Classic Qt implementation and CI evidence.
- PRs #157, #158, #159: focused QA and packaging work stacked on #151.
- PRs #136–#150: documentation/evidence reports only; consolidate or close
  duplicates during review.

## Recommended next task

Port the approved alpine wallpaper asset when it becomes available, integrate it
with `--landscape-wallpaper`, rebuild, capture three screenshots, and obtain
owner visual approval. Then provision the Mint VM and run guest acceptance.

## Files and tools

- Supervisor: `canopy_supervisor/`, `tools/canopy_supervisor.py`
- Qt: `prototype/classic/`, `.github/workflows/classic-qt.yml`
- Artwork importer: `tools/install_approved_art_zip.py`
- Mint runner: `tools/qa/classic_mint_guest_runtime.py`
- Preview packaging: `tools/qa/classic_preview_package.py`
- Screenshot validator: `tools/check_screenshot.py`
- Performance tool: `tools/measure_qt.py`

## Do not repeat

- Do not regenerate Qt prototype documentation.
- Do not relaunch the supervisor unless the existing process is gone.
- Do not claim Mint acceptance or visual approval without evidence.
- Do not push secrets or local state.
