# Compiled-Qt visual QA evidence audit

**Status: evidence audit only.** This document records what the repository's
visual QA tooling can and cannot prove. It changes no approved dock design,
no icon, no wallpaper and no image asset. It is not visual approval, not Linux
Mint acceptance and not authorization to merge to `main`.

Verified 2026-11-21. Branch `feat/canopy-supervisor-visual-qa-evidence`, base
commit `250257df8571d1ce4fa3d736f7072c4bc22dd2c1`. Host: Windows, PowerShell,
Python 3.14 (`py -3`). All commands ran with `PYTHONDONTWRITEBYTECODE=1`.

## Files audited (read only)

| File | What it actually is |
| --- | --- |
| `tools/audit_approved_icon_optics.py` | Dependency-free, read-only PNG decoder and grayscale edge-centroid **heuristic**. Verifies SHA-256 of eight locked masters, decodes RGBA without rewriting pixels, reports optical offset. Its own docstring says it is "NOT an automatic icon recenter, a visual approval or a Qt build test"; it requires `human_visual_approval_required`. |
| `tools/mint_classic_qt_smoke.py` | An **in-guest** smoke runner. It requires a real Linux Mint graphical preflight and an executable compiled Qt binary, runs three self-test screenshot processes at 1920x1080, 1200x750 and 760x500, checks Qt `SELF_TEST_PASS` markers and strict PNG structure/variation, and writes privacy-minimized JSON. Default report fields are explicitly `mint_guest_acceptance: PARTIAL_SMOKE_ONLY`, `real_application_launch: NOT_RUN`, `compositor_session_switching: NOT_RUN`, `visual_owner_approval: NOT_RUN`. |
| `docs/ICON_OPTICAL_REVIEW.md` | Diagnostic guidance. States the geometric centering assertion does not prove the illustration inside each approved image looks centered. Requires actual compiled Qt screenshots at three resolutions, per-icon bounds in a running Qt scene and an explicit human decision. Says clean CI and centroid numbers are not sufficient. |
| `tests/test_approved_icon_optics.py` | Regression and malicious-input controls for the optics audit. Uses **synthetic** generated PNGs (e.g. `make_rgba_png`) in a temp directory, not the approved masters and not Qt. Covers all five PNG filters, CRC/truncation/depth tampering, SHA and symlink rejection, path traversal and duplicate IDs. |

## Test commands and honest results

Actual commands run in the worktree, with real output excerpts:

| Command | Result | Output excerpt |
| --- | --- | --- |
| `py -3 -m unittest tests.test_approved_icon_optics -v` | **PASS** | `Ran 17 tests in 2.722s` / `OK` |
| `py -3 -m unittest tests.test_mint_classic_qt_smoke -v` | **PASS, ALL SKIPPED** | `Ran 30 tests in 0.001s` / `OK (skipped=30)` — reason: `POSIX executable-bit and shell-script semantics are unavailable on Windows`. Every test skipped; no synthetic Qt harness test executed on this host. All-skipped is not green evidence for any GUI behavior. |
| `py -3 -m unittest tests.test_foundation -v` | **PASS** | `Ran 5 tests in 0.205s` / `OK` |

No FAIL. No BLOCKED command; the smoke module is skipped by its own
`@unittest.skipIf(os.name == "nt", ...)` guard. The smoke tool has **not** been
run inside a real Linux Mint guest in this worktree. `tools/mint_classic_qt_smoke.py`
requires an absolute non-symlink compiled Qt binary, a real Mint preflight and
an output directory that does not yet exist; none of those conditions were met
here, and the tool was not invoked.

## Synthetic/offline checks vs genuine compiled-Qt screenshots

- **Synthetic / offline (what actually ran here and in Ubuntu CI):** the optics
  audit computes a numeric edge-energy centroid over locked PNG bytes; its unit
  tests use generated PNG fixtures. The smoke unit tests use `FAKE_QT`, an inert
  Python script that imitates Qt command-line output and writes hand-built PNGs.
  `docs/MINT_CLASSIC_QT_SMOKE.md` states these tests "do NOT constitute Mint
  acceptance or prove a functional compositor/session." The read-only
  `mint_acceptance_report_gate` checker validates internal evidence consistency
  only and cannot attest a genuine Mint guest or artist approval.
- **Genuine compiled-Qt screenshot (not produced here):** requires a separately
  built Qt6 Classic binary, the user's private approved-art and wallpaper bundle,
  and execution inside a real Mint Cinnamon guest. A passing run produces three
  real screenshot PNGs plus a `report.json` with measured binary SHA-256 and
  per-size SHA-256. `docs/MINT_CLASSIC_QT_SMOKE.md` records the tool as "not yet
  been run in a real Linux Mint guest." No such report or screenshot exists in
  this repository.

## Explicit statement on `main`

**No compiled Qt screenshot and no owner visual signoff exist on `main`.**
No `qt-*.png`, screenshot PNG, or smoke `report.json` is present in the
repository. The documentation consistently records owner visual signoff, real
Linux Mint guest evidence and user-facing optical approval as separate, unmet
release gates (see `docs/QUALITY.md`, `docs/ICON_OPTICAL_REVIEW.md`,
`docs/MINT_CLASSIC_QT_SMOKE.md`, `docs/MINT_GUEST_PREFLIGHT.md`,
`docs/SUPERVISOR_VERIFICATION.md`). Green CI, passing offline tests and this
evidence document must not be read as visual approval.

## Change scope

Only this document was written. No file under `canopy/assets/*`, no wallpaper,
no dock, no Qt GUI file, no `.github/workflows/review-supervisor.yml`, no
`AGENTS.md` and no `tools/review_supervisor.py` was touched. No commit, push,
merge, branch change or pull request was made; the supervisor publishes.
`PYTHONDONTWRITEBYTECODE=1` was set for every command and no `__pycache__`
remains in the worktree.
