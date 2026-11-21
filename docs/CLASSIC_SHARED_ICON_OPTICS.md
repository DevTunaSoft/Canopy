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

## Strictly opt-in candidate from prior experiment PR #109

`--icon-framing-review` selects an alternative *in-memory* source sample
inside an identical centered rounded image frame (192×192 cache with an
unchanged 168×168 clipped face). The test reuses the source-specific top
gutter measurements from #109: Browser 9px; Mail 6px; Files 2px; Calendar
0px; Photos 0px; Music 5px; Terminal 14px; Settings 14px. It is only a
candidate: trimming source gutters can alter subject size or trim baked
illustration edges. **It is never enabled by default.**

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
guard, identical outer rounded mask, untouched default path, shared provider
usage, image readiness and exact eight measured gutter constants. Compiled Qt
CI checks that `--icon-framing-review` without verified private originals
fails closed. Private original-art runtime testing is separately necessary;
synthetic Ubuntu CI cannot judge this exact artwork.

**Do not merge this candidate or declare any icon approved based on a green
test, hash match or image centroid.** Only the owner can sign off after
comparing real Qt images, and the final alpine wallpaper is a separate open
requirement.
