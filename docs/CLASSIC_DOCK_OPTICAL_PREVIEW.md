# Canopy Classic — optical dock review candidate

**Status:** Optional experiment. **NOT owner approved. NOT merged.** This
does not change the SHA-256-locked eight original PNGs or the accepted
landscape wallpaper. No artist source files are regenerated.

## Why a geometry-green dock can still look off

The 54×54 QML image slots were centered in each 58×70 dock button, but the
different *illustrations within those original icon crops* are not optically
centered. The image outlines and art details are different measurements.

The existing nonmutating `tools/audit_approved_icon_optics.py` checks the
original source SHA-256 and reports edge-energy centroids. On the original
eight source crops, large rightward detail concentrations appeared in
Calendar (+5.56% of width), original Terminal (+4.04%), Settings (+3.68%)
and Files (+2.50%). This is a **heuristic**, not a subject segmentation.

## Implementation

Run the **Qt6 compiled** Classic executable with `--optical-review`,
alongside the existing exact-art and landscape flags:

```sh
./build/classic/canopy-classic-spike \
  --approved-art-dir /absolute/path/to/exact-approved-art \
  --landscape-wallpaper /absolute/path/to/approved-alpine-wallpaper.png \
  --terminal-refinement /absolute/path/to/refined-terminal-v3.png \
  --optical-review --self-test-approved --self-test-size 1920x1080 \
  --self-test-screenshot /tmp/canopy-optical-review-1920.png
```

Repeat at `1200x750` and `760x500`. To compare, rerun the **same**
build, source inputs and screen size **without** `--optical-review`.
Always label actual Qt screenshots with exact head SHA and input hashes.

Proposed screen-pixel image offsets (X positive right, Y positive down):

| App | X | Y |
|---|---:|---:|
| Browser | +1 | 0 |
| Mail | 0 | -1 |
| Files | -1 | -1 |
| Calendar | -2 | +1 |
| Photos | 0 | -1 |
| Music | 0 | +1 |
| Terminal ORIGINAL | -2 | +2 |
| Terminal REFINED v3 | -1 | 0 |
| Settings | -2 | +1 |

Offsets are capped at **2px** in either direction, intentionally smaller
than full numerical edge-energy corrections to avoid over-adjusting
artistic framing. No zoom, crop, recolor or PNG rewriting. The entire
cached image slides within its normal dock slot, with explicit focus/hover
geometry unchanged.

**Default behavior remains unchanged**; no offsets are applied unless
the opt-in flag and exact user-approved original masters are both present.
Qt self-test checks that image rectangles correspond to expected capped
offsets and remain within dock bounds. This is **a proposal** and does not
establish visual acceptance, especially for Tux artwork intentionally
composed asymmetrically within each rounded square.

## Acceptance required before changing the default

1. Verify source SHA-256 of all eight original PNGs (the separate refined
   Terminal is always identified as an optional derivative).
2. Compile with GitHub Actions and run with the user-controlled originals.
3. Present actual Qt Before/After full screens **and same-scale enlarged dock
   crops** at all three sizes, not generated mockups.
4. Compare background, full icon art, hover/focus rings, activity dot and
   adjacent icon spacing; reject if shifting cards itself looks misaligned.
5. Obtain owner approval for the final visual, *then* and only then remove
   the temporary opt-in flag or promote an approved set of corrections.
6. Run a real Mint guest, HiDPI and keyboard focus acceptance separately.

Ubuntu CI can prove the app still compiles and the **default** Qt render
works; it cannot perform real approved-art visual review without the
private original PNGs. Avoid calling the result finished based on tests.
