# Native dock geometry port — 32/96/14/7

Status: **verified in a real Plasma session; draft review only**. No merge, no
self-approval, no visual-acceptance claim, no artwork regeneration.

## Scope and provenance

- Branch: `product/native-dock-geometry-20261127`, based on
  `ec910d7a7275296ecbc8b5e5c459d356205165d1`
  (`integration/canopy-plasma6-20261127` at task start).
- Owned paths only: `prototype/classic/Theme.qml`, `Main.qml`,
  `DockTile.qml`, this document and `scratch/native_dock_geometry/**`.
  `Main.qml` and `DockTile.qml` are byte-identical to the base; the only
  production edit is the two-line `Theme.qml` port.
- Port source: PR #729 head `cf596ddaba70c717a02106b12beb99c345279821`.
  The exact `Theme.qml` hunk was extracted with
  `git show --format= cf596dda -- prototype/classic/Theme.qml`, saved as
  `scratch/native_dock_geometry/pr729_theme_qml.patch` (SHA-256
  `164b2dee3fbf0180253818a4d293f6c690ac48c70f5916702f1cf1e1bc4bba63`),
  passed `git apply --check`, then applied. No blind cherry-pick and no
  test/asset file from the legacy PR was imported.
- Resulting constants (`Theme.qml`): `barHeight: 32`, `dockSize: 96`,
  `dockPadding: 14`, `dockSpacing: 7`; `tileSize` and `cornerRadius` unchanged.
  File SHA-256 after port:
  `f79ab1eb44c4ad953c03e17ac2f045dadadb289f89372aa118f7f19f3cffd866`.

## Real runtime evidence

Host: Windows 11. Guest: `Canopy-Test-Plasma6`, Ubuntu 26.04 LTS, real
KWin X11 session (`/usr/bin/kwin_x11`) with `/usr/bin/plasmashell` running;
CMake/Ninja/GCC/Qt6 toolchain in the guest. The full native-branch worktree
was copied into the guest, compiled there, and the compiled binary launched
with `--approved-art-dir <approved assets>` in that session.

- Source archive SHA-256:
  `441677d9311ca6e1f35474ae1c92426624d250d2c43411c0873a2eddf865c1f0`.
- Compiled binary SHA-256:
  `9f713eadb3fce76a292eb0aa68cff6e543bb6afeeb331030770cb009d7ae22eb`.
- Approved manifest SHA-256 (guest and base blob):
  `5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737`.
- `git diff ec910d7a -- prototype/classic/assets` is empty: wallpaper, icon
  masters and the manifest are byte-identical to the base. Nothing was
  regenerated or substituted.
- Foreign top-level windows were temporarily unmapped during capture and
  restored afterwards; each capture shows the launched binary's own window,
  eight approved dock icons, and the Plasma shell/panel.

Captured screenshots (real `scrot` captures, not Qt offscreen self-tests):

| Size | Path (relative to worktree) | SHA-256 |
|---|---|---|
| 1920x1080 | `scratch/native_dock_geometry/screenshots/screen_1920x1080.png` | `f65e95d17b8f5f555efdb51da23f479c0d286bcea7e8f33e613075bee845215f` |
| 1200x750 | `scratch/native_dock_geometry/screenshots/screen_1200x750.png` | `ccfcd96fa8b7841934ff947b2890fe301f83fef5e25831a2dd640948c78eae69` |
| 760x500 | `scratch/native_dock_geometry/screenshots/screen_760x500.png` | `64261840df02580f881d8f3703912ee6f8180a7cf90c95b69664e5b08fca447e` |

## Pixel measurements

`scratch/native_dock_geometry/scripts/measure_plasma.py` reads the real
captures and derives every metric from pixels: top-bar height from an
exact-RGB run ending at the border row; dock surface height from row-mean
border peaks; dock padding from the measured inset of the first 58px tile
slot; spacing from the artwork pitch (65px pitch minus the frozen 58px tile).
Full data: `scratch/native_dock_geometry/measurements/geometry.json`.
`SYNTHETIC` label does not apply: these are real-session pixels.

| Size | bar | dock | padding | spacing | tuple | surface width (measured / closure) |
|---|---|---|---|---|---|---|
| 1920x1080 | 32 | 96 | 14 | 7 | 32/96/14/7 | 541 / 541 |
| 1200x750 | 32 | 96 | 14 | 7 | 32/96/14/7 | 541 / 541 |
| 760x500 | 32 | 96 | 14 | 7 | 32/96/14/7 | 541 / 541 |

Approved tuple **32/96/14/7 is met at all three resolutions**. The prior
native screenshots measured 32/88/12/7; this port closes the 8px height and
2px inset deficits without changing artwork.

## Known out-of-scope conflict (not fixed here)

Three source-contract tests at this base still pin the legacy 88/12 values:
`tests/test_classic_qt_source.py`,
`tests/test_c100_dock_display_geometry_contract.py` and
`tests/test_classic_preview_scrollbar_theme.py`. Running them at this head
gives `Ran 27 tests, FAILED (failures=3)`, each failure a stale 88/12 pin,
not a runtime regression. Those files are outside this task's ownership and
were not edited. The exact test-side hunk from PR #729 is preserved,
**prepared but not applied**, at
`scratch/native_dock_geometry/tests_pin_sync_prepared.patch` (SHA-256
`651cdb9dbf4bd8ef3323276ed3b31e0ea4ee7c9da1bd93474ed56e0c85431a74`); it
passes `git apply --check` at this head and must be applied by the owning
worker before promotion. The Python mirror
`canopy_features/dock/display_geometry_contract.py` also retains the legacy
constants and is likewise out of scope.

## Boundaries

- Draft PR only; protected branches require distinct human approval; this
  change does not merge, promote, release or self-approve.
- No final owner visual acceptance is claimed. CI conclusions were not
  asserted as green by this work; real-session geometry PASS is the only
  claim made here.
- Resource impact: no new timer, thread, service, polling loop, dependency
  or cache. No real idle CPU/PSS measurement was taken (`NOT_RUN`); the
  change is two integer constants and cannot add runtime work.
