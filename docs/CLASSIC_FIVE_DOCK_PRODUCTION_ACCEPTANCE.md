# Canopy Classic — five-icon production pack and frozen-three acceptance

**Owner's explicit immutable scope:** **Calendar, Photos and Music are frozen.** Do not move, redraw, re-crop, relabel, replace, sharpen, or optically center them. The only dock icons authorized for correction are **Browser, Mail, Files, Terminal and Settings**.

Renderer provenance is not new artwork and is not owner visual approval. Owner visual approval and Linux Mint acceptance remain `NOT_RUN`.

## Exact v3 production pack

- Keep all **eight original approved source PNGs** and `assets/approved/manifest.json` byte-for-byte unchanged. No generated, downloaded or synthetic substitute is accepted.
- The registered production renderer is exactly `canopy-five-qt-v3`. The original approved manifest SHA-256 is `5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737`. The revised v3 pack manifest recorded with the compiled-Qt evidence is `df0b7166b0a3269d7f99484d5196633193162eba56b334b25a1ea39f9682a360` (`CI_ONLY_NOT_ON_DISK`: revised v3 pack manifest from local WS2 compiled-Qt scratch evidence, cited beside CI runs `45589523882`/`45603283480`, artifact `canopy-classic-qt-evidence`; no tracked blob matches) (`WS2_EDGE_CORRECTION_EVIDENCE.md`, evidence manifest `4fe913740bc250e6712479a3b63c426ef98856b9c3fc28271fc9b166e447af4e` (`CI_ONLY_NOT_ON_DISK`: WS2 compiled-Qt scratch evidence manifest cited by the pack evidence chain, with CI runs `45589523882`/`45603283480`, artifact `canopy-classic-qt-evidence`; no tracked blob matches)). Only Mail, Terminal and Settings changed relative to v2; Browser and Files stayed byte-identical and the three frozen icons never enter the production path.
- The compiled Qt binary exports the five icons at **192×192, 384×384 and 576×576** (15 PNGs, from the masters rather than upscaled) plus a `manifest.json`. `tools/validate_five_production_icons.py` verifies the eight source masters, exact `schema_version`, exact renderer string, source-manifest digest, all fifteen per-file SHA-256s and PNG geometry/alpha, and rejects extra files or symlinks. Those source/provenance SHA checks remain exact. An independent re-export must now prove **bounded normalized pixel identity**, not byte-identical exported PNGs: the software renderer can round a few RGB channels by one level between identical source heads.
- CI stages the exported pack at `build/classic/production-icons/` beside the binary before any approved-art run. Without that directory the binary deliberately falls back to the identical in-memory renderer; fallback is **not** proof of production-pack acceptance. The raw exported manifest SHA-256 is **not** an identity gate: the authoritative `ubuntu-24.04` run `45589523882` and later run `45603283480` recorded `3464d1d03648d8f7814f4337174691d874faa4415c38d5c245dc5fe3f09981ac` (`CI_ONLY_NOT_ON_DISK`: raw exported pack manifest from CI runs `45589523882`/`45603283480`, artifact `canopy-classic-qt-evidence` (`build/classic/production-icons/manifest.json`); not on disk), while the identical-head run `45599332103` recorded `8879e5272bad316f5dcc25e4a42666c9da89ab4472ebfbee7eeac3cf46a704d7` (`CI_ONLY_NOT_ON_DISK`: raw exported pack manifest from CI run `45599332103`, artifact `canopy-classic-qt-evidence` (`build/classic/production-icons/manifest.json`); not on disk). Decoding both CI artifacts shows only one-level RGB deltas in a few channels, no alpha changes and untouched masters. CI now runs `tools/check_five_dock_centering.py --pack-dir --reproducible-dir --approved-art-dir`, which pins the rounded RGB identity digest `ccf5bf9f09d4235a266227ed46f1f39f77e17641fd618f2f438062503a7b6bf8` (`CI_ONLY_NOT_ON_DISK`: rounded-RGB identity pin computed in CI runs `45589523882`/`45603283480`/`45599332103`, artifact `canopy-classic-qt-evidence` (`test-artifacts/five-production-pack-identity.txt`); not a tracked blob) (four-level buckets, alpha exact) and requires both exports made in the run to share it. Raw bytes are still recorded with `sha256sum` for evidence, but `sha256sum -c -` and byte-exact re-export comparisons are removed from the gate.

## Runtime activation is asserted, not inferred

The authoritative Xvfb CI must launch the compiled binary with `--require-five-production-icons` and pass its log to `tools/check_five_dock_centering.py --pack-log`. The gate accepts only exactly one `FIVE_PRODUCTION_PACK_VERIFIED` marker and no `FIVE_PRODUCTION_PACK_FALLBACK` or `FIVE_PRODUCTION_PACK_FAIL` marker; any missing, duplicated or fallback verdict fails closed and CI writes `FIVE_PRODUCTION_PACK_VERIFIED=1` only after that pass. A locally observed verified pack on a different host is not CI evidence, and a documented verified path that is `NOT RUN` in CI is not a pass.

## Frozen-pixel boundary: bounded jitter, not literal zero pixels

An earlier revision required literal zero changed frozen pixels. That claim is stale: bounded one-level compositing jitter is now allowed, with strict caps. Separate Xvfb processes round the translucent dock's software compositing by one 8-bit RGB level inside a frozen slot; the accepted bounded exception is:

- only **one RGB channel level** per pixel, with **alpha unchanged**;
- only inside the measured translucent dock plate and per frozen slot;
- at most `FROZEN_JITTER_MAX = 8` such pixels in any one frozen icon and at most `DOCK_PLATE_JITTER_MAX = 256` across the run, plus the existing at-most-two Files rounded-corner AA pixels and the bounded top-bar clock region;
- recorded in the machine-readable report as `frozen_one_level_compositing_jitter`, not silently ignored.

A two-level or larger delta, an alpha shift, a change outside the dock, a change just outside the icon slot, an excessive count, or a frozen slot whose artwork genuinely changed is still a hard `FIVE_DOCK_ICON_PIXEL_LOCK_FAIL`. All five authorized icons must still change. This is a compositing-noise exception, not permission to edit frozen artwork.

## Exported-pack identity: bounded rounded pixels, not raw bytes

`MAX_PACK_CHANNEL_DELTA = 1` caps any RGB channel difference between the two
exports made in one CI run, `MAX_PACK_CHANNELS_PER_ICON = 11` caps the changed
channels in any one density icon and in any one icon across all three
densities, and alpha must be identical.
unexpected files, wrong dimensions, invalid PNGs, larger deltas, alpha shifts,
an excess channel count and a rounded digest that differs from the pinned
v3 identity all fail closed with `V3_PACK_NORMALIZED_IDENTITY_PASS` withheld.
The four-level rounding uses `max(0, (channel - 1) // 4)` for RGB only; this
merges both observed one-level antialiasing directions but not two-level steps
at the recorded CI values. RED/GREEN unit controls cover identical exports,
one-level noise at the cap, a two-level delta, an alpha shift, an over-cap
channel count, missing/extra PNGs and a wrong pinned digest. This gate is a
raster-identity tolerance only: it does not authorize artwork edits, relax the
source-master SHA checks, or grant visual approval.

## Other CI requirements

- Capture real Qt screenshots at **760×500, 1200×750 and 1920×1080** and check exact dimensions and the bounded five-only pixel lock.
- Verify the ordinary approved startup matches the explicit five-center composition at the same resolution via `tools/check_five_dock_centering.py --frozen-identity` (bounded dynamic clock and one-level compositing noise excepted). This is an identity check: no unchanged target icon is required, but frozen artwork and every non-icon pixel stay locked; no ignored rectangle is widened.
- Preserve the existing five-minute resource measurement and unrelated agent changes.
- Preserved rollbacks: `--dock-clean-edges-review` restores the pre-centering clean-matte appearance; `--dock-original-fit` restores historical source-fit. Neither rollback reads the generated pack.
- Wallpaper integration is a separate workstream. Do not change wallpaper, QML dock geometry, controls, launcher, the eight masters or the frozen icons as part of this work.


## Evidence provenance labels

`CI_ONLY_NOT_ON_DISK` marks a hash recorded from a GitHub Actions artifact that is not
present as a tracked blob in this worktree. The five values above are retained verbatim
with their CI run IDs and the uploaded artifact name `canopy-classic-qt-evidence`; none was replaced with a
locally computed or re-normalized digest. Run `45603283480` completed successfully;
runs `45589523882` and `45599332103` completed with failure, and their artifacts remain
evidence of those runs only. Artifact retention is 14 days. These labels do not change
any source/master SHA check, pixel bound, identity pin, verdict or workflow gate, and
they do not grant owner visual approval or Linux Mint acceptance.

## Sign-off

A green run proves the v3 pack was staged with exact source/master/renderer and per-file SHA checks, that both exports share the pinned rounded pixel identity under bounded noise, and that the verified pack was loaded by the compiled binary; frozen artwork is protected within the bounded compositing exception. It does **not** prove byte-identical exported PNGs across runners, aesthetic perfection, Mint acceptance or owner visual approval. Keep Classic Qt integration draft until real Mint acceptance and owner visual approval are complete.
