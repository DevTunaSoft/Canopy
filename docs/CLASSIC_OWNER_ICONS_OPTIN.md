# Classic owner Tux icon preview opt-in (explicit, not approved)

Status: **AWAITING_CHATGPT_VISUAL_APPROVAL**. This change prepares running-instance
evidence only. It does not grant owner approval, does not change the approved
asset set, and does not authorize a merge to `main`.

## What it does

`canopy-classic-spike` gains one explicit opt-in:

```
--owner-icons-preview DIR        show the eight owner-supplied Tux PNGs from DIR
--approved-art-dir DIR           still required (unchanged approved-art gate)
```

Without `--owner-icons-preview`, startup, the eight approved icons, dock
geometry, colours, wallpaper and every existing startup marker are unchanged.
The new flag is refused (exit 2) when `--approved-art-dir` is absent or when
its PATH argument is missing. With the flag, startup fails closed (exit 3) on
any manifest, hash, path, square-size, alpha, corner or content-bounds defect
before a Qt scene is created.

## Provenance and exact bytes

- Source ZIP: `private-evidence/downloads/Canopy_Tux_Transparent_Icons.zip`
- ZIP SHA-256: `d84916fbe66f05821167c73b3fa5bde1a039547fb6f5d7969c666b1f2457415d`
- Normalization record: scratch `normalization_square.json` — crop alpha bbox
  at threshold 8, resize to an exact 1120x1120 square, center on a 1254x1254
  transparent canvas.
- The eight `prototype/classic/assets/owner_icons_20261126/icons/*.png` files
  are byte-for-byte copies of the normalized source PNGs. Their SHA-256 values
  are pinned in `prototype/classic/assets/owner_icons_20261126/manifest.json`,
  which is embedded in the binary through `CMakeLists.txt`. A caller cannot
  substitute a manifest: verification always reads the embedded copy.

| Icon | SHA-256 |
| --- | --- |
| Browser | `a6fc7c60e418cd4b7ea2c9d96141c2ebbc0e237f14d69550327d6735fd3dd6e9` |
| Mail | `5e7cff302bc2ff1f0ada410f7b74db7e9ebb8e76894c28ed1257c5752531d08a` |
| Files | `cb3282b4b246f720b0125fab0432135560acb9084ec5b1c3588dc1766713a31f` |
| Calendar | `093af486630b972395a47b4b1732c89a5fb9f1badf984f1c3d8e8b9e6e8bf267` |
| Photos | `2dde5b6084d17efb85efe97bf1d55d9b70b9ff3c62f89defee2bbbe4461a6df2` |
| Music | `be3dfeffaf0d51f8f72a005963b1f940a7cea8b996319ab66eff5dd23eb9eb62` |
| Terminal | `e9cc4b2787c1200e16f71e2058a21a9308e84dcebadd451bdb933d05e1b126cc` |
| Settings | `9b790a50a4c04eb7d579c4b9fe54e0d9b2d0d3fd0b45d58b1fa5bf256dd971d9` |

## Rendering policy

The opt-in registers `OwnerIconsPreviewProvider` as `image://canopy-dock`,
so the existing frozen `DockTile.qml` keeps its 54px art slot, 58x70 button,
alignment and accessibility names while the image source is the exact decoded
PNG bytes. No painter, matte, crop, offset, recolor or regenerated artwork is
used; Qt's ordinary Image fit to the existing 54px slot is the only scaling.

The dark frosted dock uses the scratch preview's slate face
`rgba(31,42,51,.64)` and edge `rgba(198,216,228,.20)`, applied from trusted
host code to the live `canopyDock` item only in opt-in mode. All QML dock and
tile bytes remain frozen; the approved dock is untouched at default startup.

## Startup markers

- `CANOPY_APPROVED_ART_VERIFIED: ...` — unchanged, still present in opt-in mode.
- `CANOPY_ROUNDED_DOCK_VERIFIED: ...` — unchanged in default approved mode.
- `CANOPY_OWNER_ICONS_VERIFIED: ...` — new, only when the opt-in passes.
- `CANOPY_OWNER_DOCK_FROST_ACTIVE: ...` — new, only when the opt-in passes.
- `SELF_TEST_PASS: owner exact-PNG icons and dark frosted dock at frozen 54px slots`.

## Running-binary evidence (compiled, offscreen, not a scratch HTML preview)

Build: `PATH=/c/msys64/ucrt64/bin:$PATH cmake -S prototype/classic -B <scratch>/build -G Ninja -DCMAKE_BUILD_TYPE=Release` then `cmake --build <scratch>/build --parallel 2`.

Run: the actual `canopy-classic-spike.exe` with
`QT_QPA_PLATFORM=offscreen`, `QT_QPA_PLATFORM_PLUGIN_PATH=C:/msys64/ucrt64/share/qt6/plugins/platforms`,
`QT_FORCE_STDERR_LOGGING=1`, plus
`--approved-art-dir prototype/classic/assets/approved --self-test-approved --owner-icons-preview prototype/classic/assets/owner_icons_20261126 --self-test-size WxH --self-test-screenshot PATH`.

Screenshot paths and SHA-256 values are recorded below from the real captured
PNGs; each is validated with `tools/check_screenshot.py <path> W H`.
No scratch HTML preview is cited as visual evidence.

### Captured from the compiled binary (not scratch HTML)

Binary: `private-evidence/scratch/canopy_owner_icons_build/canopy-classic-spike.exe`
SHA-256 `085a9ea0bfb795993b8e589701940c81bac745332c44870ea60ccbbceed95f28`.

| Size | Screenshot (scratch artifact) | SHA-256 | `check_screenshot.py` |
| --- | --- | --- | --- |
| 1920x1080 | `private-evidence/scratch/canopy_owner_icons_evidence/final/owner-icons-1920x1080.png` | `2837b41d18e6dfc83f5965bbe6faaebae5e3ba272fdc2f3424a34c601352fd63` | PASS |
| 1200x750 | `private-evidence/scratch/canopy_owner_icons_evidence/final/owner-icons-1200x750.png` | `f404ef3ff52cef7d31a344672a27ea503f481ef45343b2b4299b14c197b3b8c3` | PASS |
| 760x500 | `private-evidence/scratch/canopy_owner_icons_evidence/final/owner-icons-760x500.png` | `2afbb80123d4070362e8401afda20aad4304f57be111a57a526f6aef2c1c8ba6` | PASS |

Every run exited 0 and logged `CANOPY_OWNER_ICONS_VERIFIED`,
`CANOPY_OWNER_DOCK_FROST_ACTIVE`, and
`SELF_TEST_PASS: owner exact-PNG icons and dark frosted dock at frozen 54px slots`.
A default (no opt-in) run of the same binary exited 0 with no owner markers,
confirming the approved runtime is unchanged. The final re-run logs are
`.../canopy_owner_icons_evidence/final/owner-icons-WxH.log`; each has
`SELF_TEST_FAIL` count exactly 0, one `CANOPY_OWNER_ICONS_VERIFIED` and one
`SELF_TEST_PASS: owner exact-PNG icons and dark frosted dock at frozen 54px slots`.
Screenshot bytes are live offscreen Qt captures; they are **not** owner visual approval.

## Resource / evidence note

- **SYNTHETIC**: the alpha-plane negative control in
  `tests/test_classic_default_owner_icons_optin_128c973.py` uses a generated
  2x3 PNG; the byte-level manifest checks are static. They prove the gate's
  predicates, not runtime cost.
- **SYNTHETIC**: offscreen Qt software-rendered screenshots are deterministic
  captures of a live compiled window, not a Mint desktop session.
- **NOT_RUN**: real Mint compositor acceptance, long-duration idle CPU/PSS and
  owner visual approval were not measured or granted.
- **screen-reader**: dock tile `Accessible.name`/`description` are unchanged;
  no screen-reader run was performed. This opt-in changes no announcement text.
- The opt-in does not add timers, polling, services, transports or background
  wakeups. It decodes the eight existing files once at startup and keeps the
  same bounded image cache shape as the approved renderer.

## Negative controls

- Omitting `--approved-art-dir` returns exit 2 with
  `OWNER_ICONS_PREVIEW_FAIL: --owner-icons-preview requires --approved-art-dir`.
- A modified PNG returns exit 3 with `OWNER_ICON_SHA256_MISMATCH refusing substitute`.
- A missing file, symlink, non-square image, opaque corner or shifted alpha bbox
  returns exit 3 with the corresponding `OWNER_ICONS_PREVIEW_FAIL` diagnostic.
- The vetted approved runtime remains the default; the owner art never overwrites
  or replaces the approved manifest or assets.

Compiled-binary negative controls (same binary, all from actual runs):

| Invocation defect | Exit | Marker |
| --- | --- | --- |
| `--owner-icons-preview DIR` without `--approved-art-dir` | 2 | `OWNER_ICONS_PREVIEW_FAIL: --owner-icons-preview requires --approved-art-dir` |
| `--owner-icons-preview` with no PATH | 2 | `OWNER_ICONS_PREVIEW_FAIL: missing --owner-icons-preview PATH` |
| One PNG byte modified in a copied directory | 3 | `OWNER_ICON_SHA256_MISMATCH refusing substitute: icons/Browser.png` |
| One PNG removed from a copied directory | 3 | `owner icon is missing, unsafe or outside the directory: icons/Settings.png` |

Logs are in the scratch evidence directory alongside the screenshots.
