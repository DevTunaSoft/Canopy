# Canopy Classic — definitive five-icon production assets and visual lock

**Owner's explicit immutable scope:** **Calendar, Photos and Music are frozen.** Do not move, redraw, re-crop, relabel, replace, sharpen, or optically center them. The only dock icons authorized for correction are **Browser, Mail, Files, Terminal and Settings**.

## Delivery

- Keep all **eight original approved source PNGs** and `assets/approved/manifest.json` byte-for-byte unchanged. No images from a generator, internet, synthetic mockup, or an AI prompt are substitutes.
- Qt renders only the five authorized icons from the verified original masters at three separate native raster target sizes: **192×192, 384×384, 576×576**. 2x/3x versions are rendered from the masters, **not upscaled from 192px output**.
- The Qt build automatically creates `build/classic/production-icons/{1x,2x,3x}/*.png` (15 files) and `manifest.json`. The build installs these into `share/canopy/classic/icons/` with the Qt executable. The icons are not manually copied by the user.
- `source_manifest_sha256` in the generated pack is the SHA-256 of the **exact original manifest file bytes**. Each of the 15 PNGs has its own SHA-256. The runtime validates the complete set, not merely individual names, before loading even one. An absent/corrupt pack uses the identical master-derived Qt renderer instead.
- Normal approved-art Qt startup uses the five pre-rendered **1x** images, retaining only the existing small icon cache. The 2x/3x images are loaded **on demand** for high-DPI requests, avoiding extra idle RAM/CPU.
- The three frozen icons **never read any production derivative** and continue executing exactly the unchanged clean-matte image render path.

## Real Qt acceptance and rollback

The actual compiled Qt6 desktop, not a generated preview image, is captured at **760×500, 1200×750, 1920×1080**. `tools/check_five_dock_centering.py` rejects any unexpected pixel changes outside the five image slots and rejects even **one changed Calendar/Photos/Music pixel**. The immutable golden reference `docs/CLASSIC_FIVE_DOCK_GOLDEN.json` additionally stores exact 54×54 RGBA pixel SHA-256s from successful *real* Qt run [45256190360](https://github.com/DevTunaSoft/Canopy/actions/runs/45256190360), with provenance.

The 5 production per-icon golden hashes may be recorded only after Qt execution and visual examination of final build screenshots. They are **not** generated or extrapolated by AI.

Automatic CI must also:
- Hash-check all original eight masters and all fifteen production variants, reject extra files, symlinks, wrong sizes, invalid PNG checksums or nontransparent corners.
- Re-export the five icons in an independent folder and byte-compare manifests for deterministic rendering.
- Run CMake install to verify the actual packaged asset directory is populated.
- Launch the Qt binary with `--require-five-production-icons`, which fails if any pack file/hash is wrong or default mode is not selected.
- Show that the normal Qt launch matches the explicit five-center mode at the same resolution, aside from the bounded dynamic top-bar clock.
- Preserve the existing five-minute resource measurement and unrelated Hermes agent changes.

**Preserved rollback:** `--dock-clean-edges-review` restores previous pre-centering clean-matte appearance; `--dock-original-fit` restores historical source-fit. The generated pack is never used in rollback modes.

The historical blue-wave CI wallpaper is separate from the approved alpine lake master; **wallpaper integration is a different workstream**. Do not change wallpaper, QML dock geometry, controls, launcher, the eight original masters, or the three frozen icons as part of this work.

## Sign-off

A green run **proves the build is correct, source integrity is intact, and frozen pixels are protected**, not that all artwork is aesthetically perfect. Full-size real Qt screenshot inspection must precede any claim of final owner visual approval. Keep development in the Qt draft branch until the actual Linux Mint visual acceptance is complete.
