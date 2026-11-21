# Canopy Classic icon-frame alignment — second visual candidate

**Status:** opt-in, not approved, not merged. The first whole-image offset
approach ([rejected PR #108](https://github.com/DevTunaSoft/Canopy/pull/108))
made some card frames *less* centered, even though static geometry passed.
This experiment deliberately keeps all dock positions, frame dimensions,
active indicators and visual effects untouched.

## Root cause observed in the actual source art

The eight original, user-selected contact-sheet crops are 345 pixels wide
and 333–334 pixels high. They are **fully opaque** and include nonuniform,
baked-in dark gutters at their upper edges. For example, the bright
top-border transition occurs approximately 9px down in Browser, 14px down
in Settings, and 14px down in the original Terminal, but near the top in
Calendar and Photos. Fitting the entire nonsquare PNG into a square card
preserves those inconsistent dark margins. Merely shifting each QML Image
moves the whole visible card off center (the PR #108 failure).

## Proposed opt-in fix

The Qt image provider is given a `--icon-framing-review` option that works
**only with the eight exact SHA-256 verified original PNGs**. It selects a
square sampling rectangle *within each decoded source image* based on
per-icon observed top gutters. The rectangle is then drawn entirely inside
the same fixed centered 168×168px rounded mask, leaving the dock's 54×54
QML image boxes, focus rings, click targets, activity dots and spacing
**pixel-identical in position** to before.

Measured optional top-gutter trims (pixels in the original 345×334 crops):

| Browser | Mail | Files | Calendar | Photos | Music | Terminal original | Settings |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 9 | 6 | 2 | 0 | 0 | 5 | 14 | 14 |

The separately refined **Terminal v3** has its own 512×512 transparent
canvas and is **not cropped** by this experiment. No original PNG file,
SHA-256 digest, wallpaper, or default rendering path is modified. This
is a visual presentation experiment; the in-memory edge trim can still
change subject size and must be judged before any adoption.

## Real compiled Qt comparison procedure

Use the same built executable, image bundle, wallpaper, terminal candidate,
screen size and Qt rendering backend for both captures:

```sh
./build/classic/canopy-classic-spike \
    --approved-art-dir /path/to/unaltered/approved-art \
    --landscape-wallpaper /path/to/approved-alpine.png \
    --terminal-refinement /path/to/Terminal-Refined-v3.png \
    --self-test-approved --self-test-size 1920x1080 \
    --self-test-screenshot before-actual-qt.png

./build/classic/canopy-classic-spike \
    --approved-art-dir /path/to/unaltered/approved-art \
    --landscape-wallpaper /path/to/approved-alpine.png \
    --terminal-refinement /path/to/Terminal-Refined-v3.png \
    --icon-framing-review \
    --self-test-approved --self-test-size 1920x1080 \
    --self-test-screenshot candidate-actual-qt.png
```

Repeat at 1200×750 and 760×500, including enlarged dock crops at equal
scale. Verify both screenshots come from the exact GitHub compiled binary;
confirm 8 original hashes and wallpaper inputs, and prove that every
changed pixel is inside the dock icon image region. A test of centered
QML rectangles is necessary **but not sufficient** for optical approval.

If the after version still looks off, **reject it**, keep this opt-in
work in draft, and investigate whether the selected original artwork has
baked-in irregular card silhouettes that require separately approved
artist-authored derivatives. Do not move whole QML cards, silently edit
original PNGs, or call an unreviewed screenshot finished.

Linux Mint acceptance and full desktop-session integration remain separate.
