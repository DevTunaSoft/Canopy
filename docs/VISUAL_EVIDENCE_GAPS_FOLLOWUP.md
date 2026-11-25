# Compiled-Qt visual evidence gaps — follow-up audit

**Date:** 2026-11-21 (UTC). **Scope:** audit of screenshot/visual validation tooling
available on `origin/main` and in this worktree. This is a documentation-only
follow-up. No approved artwork, dock icon, wallpaper, Qt GUI file, or protected
path was changed.

**Bottom line:** the repository contains harnesses that *can* capture real
compiled-Qt screenshots, plus offline checkers and synthetic test fixtures.
It contains **no real compiled-Qt screenshots** and **no owner visual signoff**
on `main`. A green unit test or a green offline gate is not a visual acceptance.

## 1. Method and environment

- Host: Windows 11, PowerShell, Python 3.14 via `py -3`, Git for Windows.
- Worktree: `.../worktrees/visual-evidence-gaps-followup`, branch
  `feat/canopy-supervisor-visual-evidence-gaps-followup`, HEAD
  `6d26dd3a36245fd9f8034459b0843aed416dbe2b`.
- Read once: `AGENTS.md`, `docs/QUALITY.md`. Per-task rule: no full git history,
  no enumeration of all open PRs.
- `main` inventory used `git ls-tree -r --name-only origin/main` filtered for
  `\.png$|\.jpg$|screenshot|evidence|signoff` and for the known tool/doc names.
  The repository-wide glob `**/*.png` returned **no files**.
- No attempt was made to build Qt, run a real Linux Mint guest, or capture a
  real window. Those prerequisites are not present on `main`.

## 2. Tooling inventory — synthetic vs real compiled-Qt capture

| Tool / test | What it actually does | Classification |
|---|---|---|
| `tools/mint_guest_preflight.py` | Read-only environment probe. Reports `visual_acceptance: "NOT_RUN"` and a green probe is "only readiness to perform testing, not acceptance" (`MINT_GUEST_PREFLIGHT.md:18-19`). | **Synthetic / readiness only.** No Qt launched, no capture. |
| `tools/mint_classic_qt_smoke.py` | Requires an **externally compiled Qt6 binary**, approved art, wallpaper, a real Mint graphical preflight, and a lowercase 40-char source SHA. Launches three bounded `--self-test-screenshot` runs at 1920×1080, 1200×750, 760×500; counts exact `SELF_TEST_PASS:` markers, parses PNG CRC/decompressed scanlines, records per-shot SHA-256 (`mint_classic_qt_smoke.py:360-449`). | **Real compiled-Qt capture — capability only.** Not a Qt build. On `main` there is no compiled binary and no recorded run, so no real capture exists here. |
| `tests/test_mint_classic_qt_smoke.py` | Uses an inert `FAKE_QT` Python script that prints the four `SELF_TEST_PASS:` strings and writes synthetic PNGs from `zlib.compress` (`test_mint_classic_qt_smoke.py:1-4,17-80`). On Windows the POSIX executable-bit class is skipped. | **Synthetic.** Explicit docstring: "A green unit test is NOT a Mint GUI validation." |
| `tools/mint_acceptance_report_gate.py` | Offline, read-only verifier of an **existing** report directory. Never runs Qt, checks schema/hashes/PNG structure, and returns `linux_mint_execution_independently_proven: False`, `owner_visual_approval: "NOT_ESTABLISHED"` (`mint_acceptance_report_gate.py:113-122`). | **Synthetic / offline integrity.** `status=PASS` means internal consistency only, not real Mint origin. |
| `tests/test_mint_acceptance_report_gate.py` | "Synthetic PNG contract tests only: NEVER claim real Mint guest execution"; includes a negative control rejecting a fake owner-approval report. | **Synthetic.** Contract/negative-control tests only. |
| `tools/audit_approved_icon_optics.py` | SHA-locks eight source PNG masters and computes a grayscale **edge-energy centroid** in the central ~91%. Returns `human_visual_approval_required: True`; method is "not object detection" and must never auto-crop/reposition art (`audit_approved_icon_optics.py:122-126,207-214`). | **Synthetic heuristic.** Explicitly "NOT ... a visual approval or a Qt build test". |
| `tools/qa/perf_evidence_gate.py` | Bounded **offline** classifier for pre-existing Qt CPU/PSS JSON. Always sets `release_approved: False`, `visual_approval: False`. | **Synthetic / offline.** Performance evidence, not visual evidence. |
| `tools/check_shell_pack.py` | Metadata validation only — "not a runtime loader, permission sandbox, security approval or evidence of same-session switching" (`AGENTS.md:42-46`). | **Synthetic / metadata.** |
| `tools/register_classic_preview.py` | Writes/validates an opt-in desktop entry and ownership marker; no screenshot or rendering. | **Non-visual.** |

The compiled Qt prototype itself (draft PR #100) and its framing variant
(draft PR #109) are **not** on `main`: the `origin/main` tree has no `.cpp`
source and no Qt binary. The static starter `examples/shell-pack-starter/ui/Main.qml`
is a scaffold, not the Qt Classic renderer.

## 3. What a "PASS" does and does not mean

- `mint_guest_preflight` READY_FOR_TESTS = safe to attempt a test, not an acceptance.
- `mint_classic_qt_smoke` PASS = compiled Qt self-tests plus three valid PNGs
  under the identified guest. It does **not** certify visual quality, optical
  icon alignment, Nemo/Firefox launch/focus, window management, accessibility,
  crash resilience, 5-minute RAM/CPU, reboot/rollback, or an alternative session
  (`MINT_CLASSIC_QT_SMOKE.md:57-64`).
- `mint_acceptance_report_gate` PASS = internal evidence consistency only; the
  platform field is self-reported and cannot authenticate a Mint VM or capture
  chain (`MINT_ACCEPTANCE_REPORT_GATE.md:33-37`).
- `audit_approved_icon_optics` output = a diagnostic number; clean CI and edge
  centroids are not sufficient for visual signoff (`ICON_OPTICAL_REVIEW.md:29-45`).

Every tool that can emit a real capture sets owner approval to `NOT_RUN`,
`NOT_ESTABLISHED`, or `False`. None grants visual signoff by design.

## 4. Absence on `main` — verified

`git ls-tree -r --name-only origin/main` filtered for images/evidence/signoff
returned only three performance-gate files:

```
docs/QT_PERFORMANCE_EVIDENCE_GATE.md
tests/test_perf_evidence_gate.py
tools/qa/perf_evidence_gate.py
```

No `.png`/`.jpg`, no `qt-*.png` screenshots, no guest evidence directory, and
no owner signoff file are present on `main`. All screenshot evidence is
produced outside the repository, in a private Mint guest, and is not published.

The source-of-truth gap matrix `docs/RELIABILITY_99_GATE_AUDIT.md` agrees:

| Gate | Level | Question |
|---|---|---|
| R047 | BLOCKED | All eight icons optically balanced in an owner-accepted actual Qt screenshot |
| R048 | BLOCKED | Refined Terminal variant reviewed without replacing its original master |
| R049 | CI-SCOPED | Qt preview captures valid 760×500, 1200×750, 1920×1080 PNGs |
| R050 | BLOCKED | Mint guest renders the approved wallpaper and original icon set |
| R086 | BLOCKED | Actual Mint GUI acceptance runs automatically on a guest VM |
| R089 | GAP | Visual image comparison measures approved art, not just PNG dimensions |

`docs/SUPERVISOR_VERIFICATION.md:96-104` and `:133-135` likewise state that no
claim is made about real Qt screenshots or owner visual approval and that those
gates remain blocked or not run. `docs/QUALITY.md:23-24` requires the PR to
stay draft until evidence exists.

**Statement of record:** owner visual signoff and real compiled-Qt screenshots
are absent on `main`. No checked-in artifact contradicts this.

## 5. Gaps to close (not performed here)

1. Build the exact Qt source revision and record its source SHA + binary SHA-256.
2. Run `tools/mint_classic_qt_smoke.py` inside a real Linux Mint Cinnamon guest
   with the private, SHA-locked original art and alpine wallpaper.
3. Run `tools/mint_acceptance_report_gate.py` offline against that evidence with
   caller-pinned hashes; treat PASS as integrity, not acceptance.
4. Review actual captures at 760×500, 1200×750, 1920×1080 (plus HiDPI) with a
   same-scale dock zoom; obtain explicit owner visual signoff for the eight
   icons and any Terminal derivative.
5. Close R047/R048/R050/R086/R089 with exact SHA, environment, command, logs,
   screenshots and PASS/FAIL/BLOCKED status per `docs/QUALITY.md:21`.

Nothing above is a code change. Do not auto-crop, reposition, recolor, replace,
or re-approve any existing artwork or dock design as part of this audit.

## 6. Tests run for this change

Documentation-only change; the regression suite covering the audited tooling
was run with real commands. Honest status:

| Command | Result | Excerpt |
|---|---|---|
| `py -3 -m unittest tests.test_mint_classic_qt_smoke tests.test_mint_acceptance_report_gate tests.test_approved_icon_optics tests.test_mint_guest_preflight -q` | PASS | `Ran 73 tests in 1.830s` / `OK (skipped=32)` (32 POSIX-only cases skipped on Windows) |
| `py -3 tools/check_foundation.py` | PASS | `PASS: foundation files, tagline, and local Markdown links` |

NOT RUN: real Mint guest acceptance, Qt build, real compiled-Qt screenshot
capture, owner visual signoff, five-minute resource measurement — blocked by
absence of a compiled binary and a Mint guest on `main`. These are reported as
gaps in sections 4–5, not as passes.
