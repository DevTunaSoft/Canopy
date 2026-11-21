# Canopy Classic — shared dock and launcher icon optical review

**Status: DRAFT / opt-in / original masters preserved / owner approval required.**

## What the three real-Qt screenshots revealed

The outer 54×54 image item is geometrically centered, but the eight approved
PNG source crops are 345×333/334 and fully opaque. Their actual bright frame,
illustration and dark margins vary by icon; several have a visually heavy
upper or lower edge and different internal corner treatments. A geometrically
centered QML item does not imply optically centered contents.

Both the desktop dock and the searchable application launcher load the
same SHA-checked `image://canopy-dock/<app>` image provider. The imbalance
therefore repeats at 760×500, 1200×750 and 1920×1080. Correcting QML tile
positions alone would repeat the prior rejected whole-card shift (PR #108).

## Strictly opt-in source-specific candidate B (launcher only)

The earlier top-gutter-only candidate A (PR #109) did **not** consistently
improve visual centering; it worsened several icons. It is not a default.

The new `--icon-framing-review` flag selects a distinct **launcher-only**
image provider. A fixed 324×324 square sample is centered on the approximate
2%-98% bounding box of bright illustration pixels measured from each exact
SHA-256 approved 345×333/334 source image. The measured (X,Y) centers are:

| Browser | Mail | Files | Calendar | Photos | Music | Terminal | Settings |
|---|---|---|---|---|---|---|---|
| (170,170) | (172,162) | (174,164) | (173,165) | (171,166) | (172,169) | (171,170) | (175,165) |

These are a bounded visual hypothesis, **not a judgment of optical quality**.
They preserve the existing 192×192 cached icon and fixed 168×168 rounded
frame, but can change the illustration's scale and crop dark gutters.
An artist's intentionally off-center penguin may remain intentionally
off-center. Only the **launcher** can request the new provider. The frozen
dock always uses the original image provider, with the original full-image
fit, regardless of the flag. Both providers cache rendered images once,
with no per-frame animation, background service, or asset substitution.

**The candidate remains opt-in and has no owner visual approval.**

The command immediately refuses the option unless the complete **eight
exact SHA-256 approved original images** are verified. Neither the manifest
nor any original image is rewritten or published.

For the same compiled Qt executable, same private icon archive and same
wallpaper, capture BOTH desktop and open launcher before and after:

```sh
# baseline (the current visual behaviour)
canopy-classic-spike --approved-art-dir /private/approved-art \
    --self-test-approved --self-test-size 1200x750 \
    --self-test-screenshot /private/baseline-desktop.png \
    --self-test-launcher-screenshot /private/baseline-launcher.png

# opt-in alternative (must keep the same original input bytes)
canopy-classic-spike --approved-art-dir /private/approved-art \
    --icon-framing-review --self-test-approved --self-test-size 1200x750 \
    --self-test-screenshot /private/candidate-desktop.png \
    --self-test-launcher-screenshot /private/candidate-launcher.png
```

Repeat at 760×500 and 1920×1080. For private comparisons, measure:
- Outer-frame rectangle and aligned image center in **dock and launcher**;
- Material change only inside the expected icon face regions, not top bar,
  wallpaper, dock background, focus outlines or sample Files window;
- Individual icon optical centroids and visible clipping, not just QML item
  centers; detect inconsistent size, black gutters or cutoff penguin details;
- Terminal and Settings at an enlarged but *same-scale* view, with Original
  or Terminal-v3 derivative provenance explicitly noted;
- Original source hash conservation and no user art uploaded to public CI;
- Actual Linux Mint Qt guest performance and visual QA, separately from the
  permitted Debian/Xvfb private reproduction.

## Automated CI vs visual acceptance

`tests/test_classic_shared_icon_framing.py` verifies the explicit opt-in
guard, identical outer rounded mask, untouched default path, separate
dock and launcher image providers in opt-in mode, image readiness and exact
eight measured gutter constants. Compiled Qt
CI checks that `--icon-framing-review` without verified private originals
fails closed. Private original-art runtime testing is separately necessary;
synthetic Ubuntu CI cannot judge this exact artwork.

**Do not merge this candidate or declare any icon approved based on a green
test, hash match or image centroid.** Only the owner can sign off after
comparing real Qt images, and the final alpine wallpaper is a separate open
requirement.

## Repeatable byte-exact difference audit (stdlib only)

After six actual Qt captures from **one and the same compiled executable**,
with the original icons verified, put both modes' PNGs in a local directory.
Use the exact naming scheme:
`baseline-{desktop|launcher}-{760x500|1200x750|1920x1080}.png` and
`framed-{desktop|launcher}-{760x500|1200x750|1920x1080}.png`.

```sh
python3 tools/check_classic_icon_frame_diff.py \
  --evidence-dir /private/qt-optical-evidence \
  --output /private/qt-optical-evidence/alignment-difference.json
```

The checker reuses the repository's bounded **stdlib RGBA PNG decoder**,
verifies CRC, image dimensions and symlinks. It requires the
**entire closed desktop and dock to remain pixel-identical**, while the
experimental launcher may change only within its eight fixed icon slots.
It compares both interfaces at all three sizes.
The declared pixel centers are valid only for this branch's source layout;
layout changes require a new recorded review, not an automatic geometry
tolerance expansion. Eight synthetic PNG regression tests cover changed
background pixels, wrong interface, wrong dimensions, truncation/CRC,
symlinks and unchanged icons.

This audit proves only that pixel changes are confined to icon slots,
**not** that the artwork has become centered or that the new framing looks
better. A nonuniform result is grounds to reject the candidate even if
the six pixel-diff comparisons succeed.

## Independent fractional high-DPI issue exposed during this review

At `QT_SCALE_FACTOR=1.5`, the *old compiled* desktop captured the real
1200×750 logical window as an **1800×1125 physical-pixel PNG**, then
falsely rejected the open launcher because it compared its physical
screenshot dimensions against the unscaled logical window dimensions.
This was a test-instrumentation defect, not proof the icon image failed
to load.

The patch now compares the two **actual QImage pixel sizes from the same
run** instead, preserving a strict equality check without assuming 1×
device pixel ratio. A compiled Qt Actions step captures and validates
desktop+launcher images at **125%, 150%, and 200% scale**, checks full
PNG content and verifies the pair is not byte-identical. Source guards
in `tests/test_classic_hidpi.py` preserve this behavior.

This does not mean fonts, icons and accessibility are visually
approved at HiDPI; those still need real-source, real-display and Linux
Mint reviews independently.

## Dock freeze, owner correction (November 21)

The accepted dock placement and rendering must NOT participate in launcher
experiments. The launcher overlay no longer toggles `canopyDock.visible`.
The existing `image://canopy-dock` renderer is ALWAYS instantiated with
`framingReviewMode=false`. An optional second, private
`image://canopy-launcher-review` provider is created only with
`--icon-framing-review` and used exclusively by LauncherOverlay.qml.

A runtime or visual diff must reject **even one changed desktop pixel**
between normal and candidate modes. This is stronger than the prior
"changes only within any icon rectangle" policy, which wrongly permitted
alteration of the dock. These gates do not endorse any optical candidate;
the source portraits still require icon-by-icon design review.
