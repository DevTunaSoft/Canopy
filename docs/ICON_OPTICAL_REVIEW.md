# Canopy Classic icon optical review — compiled dock, measured, not owner approval

**Status:** engineering measurement of the compiled Classic dock at integration
tip `ec4ccc65a07071f85c0ce627447bc06c0dc3e0ad`. This documents what changed and
what was measured; it is **not** owner visual approval, not Linux Mint
acceptance, and it does not authorize a redesign. No approved master image,
wallpaper or dock chrome was generated, replaced or resampled.

## Why this review exists

The Qt geometry self-test proves that eight 54×54 art rectangles are centred
on their 58×70 buttons. That does not prove the illustration *inside* each
SHA-locked PNG looks centred, nor that the interaction chrome is consistent.
The owner's mock-up complaint was therefore investigated against real compiled
captures rather than by editing artwork.

## What changed (owned files only)

- `prototype/classic/DockTile.qml`: the art slot stays exactly `54` px and is
  now named `artSize`; the hover/focus plate is one consistent **62px** square
  (`54 + 4px` on each side, radius 18), centred on the same art centre, with a
  one-step contrast increase (`#3dffffff` hover / `#24ffffff` focus). The plate
  remains `visible: tile.hovered || tile.activeFocus`, so it is interaction
  chrome only — it never paints into an idle capture and never samples,
  crops or recolors approved artwork.
- `tools/check_five_dock_centering.py`: added a read-only `--optical-centroids`
  diagnostic mode and `PRESENTATION_BOX_PX = 62`. The existing pixel lock,
  jitter bounds and v3 pack identity gate are unchanged.
- `tests/test_classic_five_icon_runtime_mode.py`: source contracts for the 62px
  plate, the frozen 54px art slot and the diagnostic's fail-closed behaviour.

`RoundedDockIconProvider.cpp` and `Theme.qml` were reviewed but deliberately
**not edited**: see the crop/offset and plate-contrast decisions below.

## Method and exact artifacts

Real MSYS2 UCRT64 Qt 6 / Ninja compile of the same worktree, capture with
`--self-test-approved --self-test-size <WxH>` at all three required sizes,
software offscreen renderer (`QT_QPA_PLATFORM=offscreen`,
`QT_QUICK_BACKEND=software`). Every capture exited 0 with 21 `SELF_TEST_PASS`
markers and passed `tools/check_screenshot.py` at its exact dimensions.

| Artifact | Before (`ec4ccc6`) | After (refinement) |
|---|---|---|
| 1920×1080 PNG SHA-256 | `72afd14ef4d3200ca5d418b3df912dd9c5f0b16fbcd1a50fc96b332e12a8f8ed` | `3f1809c0d9f943b1138c7686acd6a416d49e9b4219aa2fe5df08e9fb45551bca` |
| 1200×750 PNG SHA-256 | `8a186ba3676550d99a47d943abcea980fc99123a986f16ad500dd0884a64a03e` | `1e6d428d6befb260a53769590a017082cf5f8dec1bbb842e41bd416c238cac0b` |
| 760×500 PNG SHA-256 | `b278e2c58c2d6ded729edfefd9beb4b699ca8075a0dfa7efc2518b21b656c3d5` | `453943c06cfa0197a8078bbfc0a344e9b12bf2c6409e9ee32b121e072c5e97fb` |

Windows Qt writes colour-type 2 (RGB) PNGs; the stdlib gate decodes RGBA. Lossless
RGB→RGBA wrappers (`before-rgba-*`, `after-rgba-*`) were verified pixel-for-pixel
before gating. Full per-file digests, including both binary hashes, are in the
PR evidence bundle; the combined report SHA-256 is
`9e376bd726d0d03e5626e4466e7516b6d91fc1cd97815c902a05b19c4d55b144`.

## Center alignment (measured, not eyeballed)

`tools/check_five_dock_centering.py --optical-centroids` computes an
**edge-energy centroid** inside the central ~91% of each 54px slot, using the
same frozen/target inventory and slot geometry as the pixel lock. Positive dx
is right, positive dy is below the slot centre. Values are from the 1920×1080
capture; 1200×750 agrees to 0.01px:

| Icon | dx (before → after) | dy (before → after) | Classification |
|---|---|---|---|
| Browser | +0.167 → +0.167 | +0.368 → +0.368 | five-target |
| Mail | +1.048 → +1.048 | +2.035 → +2.035 | five-target |
| Files | +2.395 → +2.395 | +1.502 → +1.502 | five-target |
| Terminal | +1.740 → +1.740 | +2.486 → +2.486 | five-target |
| Settings | +0.675 → +0.675 | +0.717 → +0.717 | five-target |
| Calendar / Photos / Music | unchanged | unchanged | frozen |

The 760×500 diagnostic reports a uniform +15px dy for *all eight* slots — that
is a known sampling offset of the small-scene slot centre, identical before and
after, so it is recorded but not treated as an icon defect.

## Crop/offset decision

The provider's five-target map (`kFiveDockCenterOffsets`, all |x|,|y| ≤ 9)
and its source matte trims already encode the bounded WS2 correction. The
remaining measured deltas are ≤2.5px in the art slot and are heuristic edge
energy, not object segmentation. Changing them would alter the SHA-locked
`canopy-five-qt-v3` pack and invalidate the pinned normalized identity
(`ccf5bf9f…`) plus its CI gate. **No crop or offset change is justified by
this measurement**; a larger correction needs owner visual approval. The
provider is therefore byte-identical and no master is rewritten.

## Plate contrast decision

The plate contrast sample below uses dock-plate gutter luminance against the
wallpaper immediately above the dock, from the after captures: Michelson contrast 0.3102 (1920×1080), 0.2880
(1200×750) and 0.0412 (760×500, where the sample crosses a lighter wallpaper
band). The dock silhouette is unambiguous at the two larger sizes; the small
scene is weaker but unchanged. This is a scoped offscreen measurement, not a
contrast-audit acceptance. Within the owned files the only plate that can be
changed without editing the frozen dock chrome in `Main.qml` is the tile
interaction plate, which is what this change refines.

## Consistent 62px presentation

Every tile now derives its interaction frame from a single `presentationSize:
62` property; the 54px art is unchanged and the 4px ring is equal on all sides.
This matches the 62×62 optical crop used by the frozen-five evidence and
removes the old 56px/54px mismatch. The compiled geometry gate still bounds the
art to 50–56px, so the presentation frame cannot silently become a second art
slot.

## Exact before/after pixel evidence

`tools/check_five_dock_centering.py --frozen-identity` on the lossless RGBA
wrappers, same renderer, one capture per size on each side:

| Resolution | Changed pixels (any of the eight icons) | Frozen jitter | Clock-only pixels | Non-icon changes |
|---|---|---|---|---|
| 1920×1080 | 0 for all eight | 0 | 618 | 0 |
| 1200×750 | 0 for all eight | 0 | 203 | 0 |
| 760×500 | 0 for all eight | 0 | 203 | 0 |

The only differing pixels are live top-bar clock digits. `--frozen-identity`
still rejects any frozen-artwork edit, alpha shift, out-of-dock change or excess
one-level compositing noise; `FROZEN_JITTER_MAX=8`, `DOCK_PLATE_JITTER_MAX=256`
and the card-silhouette probes are untouched. The bounded compositing jitter
gate is intact and passes with zero jitter consumed.

## Approvals and evidence classification

- Approved masters from `f86c17b`: byte-identical, never regenerated or replaced.
- Five-target identity: preserved (0 changed pixels); no measured correction
  applied because none is justified at this time.
- Owner visual approval: **NOT_RUN** — the owner's counterpart owns visual
  judgement; these numbers do not infer it.
- Linux Mint guest acceptance: **NOT_RUN**. Ubuntu Xvfb CI: authoritative for
  capability/GIO/screenshot gates; not duplicated here.
- Resource note: measured compile-time Qt work and bounded Python capture/gate
  work on this host; real-runtime idle PSS/CPU: `NOT_RUN` (no new runtime timer,
  thread, effect item or per-frame work — the plate is a static Rectangle bound
  to existing hover/focus state). Timing microbenchmark: `SYNTHETIC` — not used
  for any claim. Screen-reader behaviour unchanged: no accessibility name,
  description or announcement code was edited. The change cannot trade
  stability, security, accessibility or approved visuals for a minor gain: it
  touches only one centered interaction Rectangle plus diagnostics.
- No merge into `main`; draft PR only.

## Source-master audit (retained from the previous review)

The original eight source PNGs are opaque 345×333/334 crops with different
internal compositions. Never "fix" this by overwriting or regenerating the
SHA-locked originals. The dependency-free master audit remains available:

```sh
python3 tools/audit_approved_icon_optics.py \
  --approved-art-dir /path/to/approved-art \
  --manifest /path/to/classic/prototype/classic/assets/approved/manifest.json \
  --output icon-optics-report.json
```

It verifies SHA-256 for all eight originals, decodes their RGBA streams without
rewriting files, and computes a center of high-contrast grayscale edge energy
in each source's central ~91%. Positive offset means edge detail falls to the
right or below the geometric center. This is a **heuristic**, not object
segmentation: decorative corners, gradients, shadows, Tux and foreground shapes
affect it. Do **not** automatically crop, reposition or recolor artwork from
these numbers. Any icon-specific optical adjustment must be a distinct,
reproducible derivative preview reviewed against **actual Qt runtime captures**
and 8-source SHA evidence. A complete acceptance pass still needs the original
manifest/digest evidence, any derivative clearly identified, compiled captures
at 760×500, 1200×750 and 1920×1080 with no substituted wallpaper, per-icon
visual bounds in a running scene, an explicit human visual decision (clean CI
and edge-centroid numbers are not sufficient), and a true Linux Mint guest test.
