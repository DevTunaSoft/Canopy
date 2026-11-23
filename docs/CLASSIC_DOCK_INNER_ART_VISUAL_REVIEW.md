# Canopy Classic: opt-in inner-art dock framing review

**Status: draft visual experiment; NOT accepted.** Scope: [icon alignment #85](https://github.com/DevTunaSoft/Canopy/issues/85). Based exactly on compiled Classic source branch `feat/classic-qt-port-buildable-20261121` at `07853e9566d466e48ac01b8bbf6332357a45f119`.

## Why this is not the rejected whole-card shift

The original eight PNG contact-sheet crops have unequal internal gutters. The rejected [PR #108](https://github.com/DevTunaSoft/Canopy/pull/108) moved whole QML cards and made Calendar/Settings look worse. **This candidate never moves a button, image rectangle, outer alpha mask, focus halo, active dot, dock glass surface, or asset file.** It reuses the existing, already source-audited launcher internal-content sampling algorithm and enables it for the dock *only* with an independent opt-in flag.

In `--dock-inner-framing-review`, the existing provider samples bounded, icon-specific 324×324 regions *inside the eight SHA-verified original PNG sources*, then draws them within the same 168×168 rounded face. Without the flag, the original full-image fit is byte-for-byte the existing default. The separate optional Terminal v3 derivative is not internally reframed. There are no extra image providers, background workers, shader effects, animations, or frame-time polling.

The provider already contains the source-art center measurements. This is **not an automatic aesthetics algorithm** and does not imply the result is better. The outer frame must stay centered; the new candidate may still make some foreground artwork look too large. If the owner rejects it, keep default unchanged and do not promote the flag.

## Evidence after the draft PR workflow finishes

The CI workflow **builds one actual Qt6 executable** and takes the unchanged baseline screenshots at all three required sizes. It then uses that **same executable**, the same eight repo SHA-verified approved PNGs and the same software render backend to capture candidate screenshots:

- `classic-{size}.png`: unchanged default
- `dock-inner-review-{size}.png`: opt-in content candidate
- `dock-inner-frame-diff-{size}.json`: verified changed-pixel counts by icon, wallpaper/dock exclusion and precise hashes
- `dock-inner-review-{size}.log`: runtime markers proving the candidate mode was activated

The three sizes are `1920x1080`, `1200x750`, and `760x500`. The pixel comparison must reject any change outside the 54px icon rectangles, aside from the clock's strict right-hand top-bar region in case a minute rolls over. It also checks the four corner-mask pixels on each card, each icon having actual changed content, and invalid/missing PNGs or unapproved-source mode rejection. These are **mechanical isolation checks, not aesthetic approval**.

When available, substitute the owner's approved alpine/autumn scene using the **existing** `--landscape-wallpaper PATH` option in the same-binary review. The current headless screenshot comparison deliberately uses the historical blue-wave fixture; the original alpine wallpaper remains **unapproved/not integrated**. Do not call this a final wallpaper review.

## Non-negotiable acceptance

Do not merge to `main` or make the flag default without explicit owner signoff on **genuine full-size, compiled Qt screenshots**, including readable enlarged dock crops. Do not rewrite, crop on disk, recolor, resize, rename or rehash any of the approved original eight icon masters. Do not modify the frozen `DockTile.qml`, `Main.qml` dock block, `Theme.qml` geometry, manifest, original wallpaper or other workstreams. This PR is not a Linux Mint session test or release acceptance.

**Reproduction:**

```sh
python3 -m unittest tests.test_classic_dock_frozen tests.test_classic_shared_icon_framing tests.test_dock_inner_framing_review -v
# With approved art, run the compiled binary twice at each size:
./build/classic/canopy-classic-spike --approved-art-dir prototype/classic/assets/approved --self-test-approved --self-test-size 1200x750 --self-test-screenshot baseline.png
./build/classic/canopy-classic-spike --approved-art-dir prototype/classic/assets/approved --dock-inner-framing-review --self-test-approved --self-test-size 1200x750 --self-test-screenshot candidate.png
python3 tools/check_dock_inner_framing.py --before baseline.png --after candidate.png --size 1200x750
```
