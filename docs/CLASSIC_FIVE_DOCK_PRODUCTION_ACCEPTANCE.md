# Canopy Classic — five-icon production pack and frozen-three acceptance

**Owner's explicit immutable scope:** **Calendar, Photos and Music are frozen.** Do not move, redraw, re-crop, relabel, replace, sharpen, or optically center them. The only dock icons authorized for correction are **Browser, Mail, Files, Terminal and Settings**.

Renderer provenance is not new artwork and is not owner visual approval. Owner visual approval and Linux Mint acceptance remain `NOT_RUN`.

## Exact v3 production pack

- Keep all **eight original approved source PNGs** and `assets/approved/manifest.json` byte-for-byte unchanged. No generated, downloaded or synthetic substitute is accepted.
- The registered production renderer is exactly `canopy-five-qt-v3`. The original approved manifest SHA-256 is `5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737`. The revised v3 pack manifest recorded with the compiled-Qt evidence is `df0b7166b0a3269d7f99484d5196633193162eba56b334b25a1ea39f9682a360` (`WS2_EDGE_CORRECTION_EVIDENCE.md`, evidence manifest `4fe913740bc250e6712479a3b63c426ef98856b9c3fc28271fc9b166e447af4e`). Only Mail, Terminal and Settings changed relative to v2; Browser and Files stayed byte-identical and the three frozen icons never enter the production path.
- The compiled Qt binary exports the five icons at **192×192, 384×384 and 576×576** (15 PNGs, from the masters rather than upscaled) plus a `manifest.json`. `tools/validate_five_production_icons.py` verifies the eight source masters, exact `schema_version`, exact renderer string, source-manifest digest, all fifteen per-file SHA-256s and PNG geometry/alpha, and rejects extra files or symlinks. An independent re-export must byte-match the staged pack.
- CI stages the exported pack at `build/classic/production-icons/` beside the binary before any approved-art run. Without that directory the binary deliberately falls back to the identical in-memory renderer; fallback is **not** proof of production-pack acceptance. The exact v3 pack manifest SHA-256 observed on the authoritative `ubuntu-24.04` runner is `3464d1d03648d8f7814f4337174691d874faa4415c38d5c245dc5fe3f09981ac` (CI run `45589523882`); CI checks it with `sha256sum -c -` and also proves a byte-identical second export.

## Runtime activation is asserted, not inferred

The authoritative Xvfb CI must launch the compiled binary with `--require-five-production-icons` and pass its log to `tools/check_five_dock_centering.py --pack-log`. The gate accepts only exactly one `FIVE_PRODUCTION_PACK_VERIFIED` marker and no `FIVE_PRODUCTION_PACK_FALLBACK` or `FIVE_PRODUCTION_PACK_FAIL` marker; any missing, duplicated or fallback verdict fails closed and CI writes `FIVE_PRODUCTION_PACK_VERIFIED=1` only after that pass. A locally observed verified pack on a different host is not CI evidence, and a documented verified path that is `NOT RUN` in CI is not a pass.

## Frozen-pixel boundary: bounded jitter, not literal zero pixels

An earlier revision required literal zero changed frozen pixels. That claim is stale: bounded one-level compositing jitter is now allowed, with strict caps. Separate Xvfb processes round the translucent dock's software compositing by one 8-bit RGB level inside a frozen slot; the accepted bounded exception is:

- only **one RGB channel level** per pixel, with **alpha unchanged**;
- only inside the measured translucent dock plate and per frozen slot;
- at most `FROZEN_JITTER_MAX = 8` such pixels in any one frozen icon and at most `DOCK_PLATE_JITTER_MAX = 256` across the run, plus the existing at-most-two Files rounded-corner AA pixels and the bounded top-bar clock region;
- recorded in the machine-readable report as `frozen_one_level_compositing_jitter`, not silently ignored.

A two-level or larger delta, an alpha shift, a change outside the dock, a change just outside the icon slot, an excessive count, or a frozen slot whose artwork genuinely changed is still a hard `FIVE_DOCK_ICON_PIXEL_LOCK_FAIL`. All five authorized icons must still change. This is a compositing-noise exception, not permission to edit frozen artwork.

## Other CI requirements

- Capture real Qt screenshots at **760×500, 1200×750 and 1920×1080** and check exact dimensions and the bounded five-only pixel lock.
- Verify the ordinary approved startup matches the explicit five-center composition at the same resolution via `tools/check_five_dock_centering.py --frozen-identity` (bounded dynamic clock and one-level compositing noise excepted). This is an identity check: no unchanged target icon is required, but frozen artwork and every non-icon pixel stay locked; no ignored rectangle is widened.
- Preserve the existing five-minute resource measurement and unrelated agent changes.
- Preserved rollbacks: `--dock-clean-edges-review` restores the pre-centering clean-matte appearance; `--dock-original-fit` restores historical source-fit. Neither rollback reads the generated pack.
- Wallpaper integration is a separate workstream. Do not change wallpaper, QML dock geometry, controls, launcher, the eight masters or the frozen icons as part of this work.

## Sign-off

A green run proves the exact v3 pack was staged, hash-checked and loaded by the compiled binary, and that frozen artwork is protected within the bounded compositing exception. It does **not** prove aesthetic perfection, Mint acceptance or owner visual approval. Keep Classic Qt integration draft until real Mint acceptance and owner visual approval are complete.
