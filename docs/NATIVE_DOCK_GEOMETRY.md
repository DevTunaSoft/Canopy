# Native Classic dock geometry (32/96/14/7)

## Authority and bounded scope

- Governing directive: Rev3
  `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md`,
  SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a`.
  Its PR #729 section requires restoration of the previously approved geometry
  `32/96/14/7` with no unapproved redesign and with approved artwork/identity
  preserved.
- Base: `integration/canopy-plasma6-20261127` at
  `ec910d7a7275296ecbc8b5e5c459d356205165d1`. That native base reproduces
  `32/88/12/7` in `prototype/classic/Theme.qml`.
- Workstream branch: `product/dock-geometry-32-96-14-7-20261128` from that exact
  base. Owned paths are strictly `prototype/classic/Theme.qml`,
  `docs/NATIVE_DOCK_GEOMETRY.md` and `scratch/dock_geometry_fix/**`.
- PR #729 (legacy branch) and PR #737 (native branch) are left untouched. This
  is a separate bounded draft for review, not a merge, promotion, approval or
  release action.

## Exact constants

In `prototype/classic/Theme.qml`:

| Constant | Base (`ec910d7a`) | This head | Required |
|---|---:|---:|---:|
| `barHeight` | 32 | 32 | 32 |
| `dockSize` | 88 | **96** | 96 |
| `dockPadding` | 12 | **14** | 14 |
| `dockSpacing` | 7 | 7 | 7 |

`barHeight` and `dockSpacing` were already correct and were not edited. Only
lines 17 and 18 changed (`dockSize 88 -> 96`, `dockPadding 12 -> 14`); every
other Theme.qml byte, all other QML/C++ and all approved assets are unchanged.
No wallpaper or icon was regenerated, resized, substituted or overwritten.

## Headless byte-level geometry projection

Artifact: `scratch/dock_geometry_fix/geometry_projection.json`, produced by
`scratch/dock_geometry_fix/project_geometry.py` with no Qt, display, screenshot
or pixel sampling. Classification: `STATIC SOURCE ONLY` / `SYNTHETIC`. The
projection is pinned to commit `672e46809751d96606b3f6986c5cfe0535ee6e38`, the
latest commit touching `Theme.qml`; later documentation/evidence-only commits
do not change any projected value.

- Base tuple reproduced `32/88/12/7`; head tuple exactly `32/96/14/7`.
- Non-geometry Theme.qml projection SHA-256 is identical at base and head:
  `aca44d138d4cc6c5ac82cc271be6633c5cd95f54882c3e6ee1bcd908b3ce7cc3`.
  This proves colors, identity tokens, tile/radius constants and all other
  visual inputs stayed byte-frozen; only the two geometry constants moved.
- Projected dock surface width, using the committed `DockTile.qml` width 58 and
  eight icons: `8*58 + 7*7 + 2*padding` = **537 px** at base (padding 12) and
  **541 px** at head (padding 14); dock height 88 -> 96, bar height 32.
- Every git blob under `prototype/classic/assets/` is byte-identical between
  base and head (empty changed-blob set), including the approved wallpaper,
  the eight icon masters and the manifest.

This is a projection of committed bytes only. It is not a compile, a render, a
same-binary pixel diff or a native Plasma observation.

## Visual-input freeze tests (run, not assumed)

Command (per worktree root, `PYTHONPATH` set to that root):
`python3 -m unittest -v` over `tests.test_classic_dock_frozen`,
`tests.test_classic_qt_source`,
`tests.test_classic_preview_scrollbar_theme`,
`tests.test_c100_dock_display_geometry_contract`,
`tests.test_classic_status_a11y`,
`tests.test_nd041_native_settings_controls_wiring`,
`tests.test_check_visual_lock`, `tests.test_check_visual_region_identity` and
`tests.test_classic_clock_accessibility_no_visual_change`.

- Pristine detached base worktree at `ec910d7a`: `Ran 79 tests ... OK`, rc=0.
- Remediation head: `Ran 79 tests ... FAILED (failures=3)`, rc=1.
- The three new failures are exactly:
  `test_frozen_visual_constants_are_unchanged`,
  `test_theme_identity_tokens_frozen`,
  `test_mirrors_match_frozen_classic_ui_source`.
  All three assert the superseded `dockSize: 88` / `dockPadding: 12` pins in
  test files outside this workstream's ownership. No test file was edited, so
  the stale-pin red is reported honestly as
  `EXPECTED_STALE_PIN_RED_FROM_APPROVED_GEOMETRY`, not suppressed and not
  relabelled as a pass. The remaining 76 tests pass at head.
- `python3 tools/check_foundation.py`: `PASS: foundation files, tagline, and
  local Markdown links`, rc=0.

## Acceptance status

- Pixel / visual owner acceptance: **HOLD / NOT_RUN**. No screenshot was
  captured or sampled, no same-binary pixel diff was performed, and no owner
  visual approval is claimed. Final visual acceptance stays owner-gated.
- Real compiled Qt: `NOT_RUN`. Native Plasma / Mint guest acceptance:
  `NOT_RUN`. CI conclusions are not asserted.
- Screen-reader behavior: `NOT_RUN` (this change only edits two integer
  constants and touches no accessibility path).

## Resource / evidence note

- Measured: `SYNTHETIC` — source-contract tests, headless byte-level geometry
  projection and git blob identity only, on the Windows host.
- Deliberately not measured: `NOT_RUN` — native Qt compile and launch, real
  desktop idle CPU/PSS, long-duration sampling, screen-reader behavior and
  visual/pixel acceptance.
- Two integer constant edits add no timer, thread, service, polling loop,
  dependency, cache or runtime work. No stability, security, accessibility or
  approved-visual trade was made for a minor gain.

## Evidence index (SHA-256 from current bytes)

| Artifact | SHA-256 |
|---|---|
| `scratch/dock_geometry_fix/project_geometry.py` | `13d71d99b17ac7e7325ea8712fee2265aab755dc36d701bb1531b88fed132884` |
| `scratch/dock_geometry_fix/geometry_projection.json` | `57b75938d019aae2e9ee916b6bcacbc8b75143754cb1a7f2dbc0f16ebdef8f77` |
| `scratch/dock_geometry_fix/freeze_tests/summarize_freeze.py` | `679ff033628c964a7b6f6aec5f7c9ba5a543ffaffdb365e91356fc8f0575d1ca` |
| `scratch/dock_geometry_fix/freeze_tests/summary.json` | `24168b0d0d70fceb3389208160cbadd4a8d5afc50c5e9451a5aa4cff63c431bb` |
| `scratch/dock_geometry_fix/freeze_tests/base_freeze.log` | `41e3ce630d48c0e9a058bf627df78773c13a4322b6496413314c82d20906d0e7` |
| `scratch/dock_geometry_fix/freeze_tests/head_freeze.log` | `e991cec7a57763d91112a2e111f60554c84b3fe7dab13044c617661bde620725` |
| `scratch/dock_geometry_fix/freeze_tests/foundation.log` | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| `scratch/dock_geometry_fix/freeze_tests/projection_run.log` | `aff84fe98759b4508d48a4a96c945d3e084727ab40425cde0313904b636fbf9d` |
| Theme.qml blob at base (`git show ec910d7a:...`) | `aff938cabd9065a0cb091f98f97a2af948a81fd549022463307ea0f11f8ec54d` |
| Theme.qml blob at head (`git show HEAD:...`) | `f79ab1eb44c4ad953c03e17ac2f045dadadb289f89372aa118f7f19f3cffd866` |

## Boundary

Open as one draft PR against `integration/canopy-plasma6-20261127`. Do not
merge, promote, release, self-approve or treat this as owner final visual
acceptance. No CI green conclusion is claimed.
