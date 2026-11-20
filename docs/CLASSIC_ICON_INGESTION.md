# Original Canopy Classic icon ingestion (review-only)

Use `tools/prepare_classic_icons.py` to stage **eight manually reviewed, individually prepared RGBA PNG assets** matching the exact selections in `classic-approved-selections.json`. It will **never** extract random tiles from an old comparison sheet, assume placeholder SVGs are approved, or fabricate missing images.

## Required input filenames

The approved option number is part of each filename: `browser-option-3.png`, `mail-option-5.png`, `files-option-2.png`, `calendar-option-3.png`, `photos-option-2.png`, `music-option-3.png`, `terminal-option-4.png`, and `settings-option-8.png`.

All inputs must be 8-bit RGBA noninterlaced PNGs, 256–2048 pixels per side, at most 4 MiB each. The tool validates PNG container structure, CRC, dimensions and selected names. **It does not certify visible transparency, artistic quality, security against every malformed compressed stream, provenance, trademark safety, or permission to distribute Tux.** Source artwork is not present in the repository yet.

## Offline staging

```bash
python3 tools/prepare_classic_icons.py --source path/to/reviewed-pngs --output /tmp/canopy-classic-approved-stage
python3 -m unittest tests.test_classic_icon_ingestion -v
```

The output is an empty/new folder containing `browser.png` through `settings.png`, `classic-icons.qrc` with resource prefix `/canopy/classic/icons`, and `staged-icons.json` marked `review_only_not_release_approved`.

This is **not currently wired into CMake, Qt, the dock or the launcher**, deliberately. Require human visual comparison at 24, 48, 64, 128px, copyright and provenance audit (including original Tux attribution to Larry Ewing/GIMP), UI screenshot review on the real Qt runtime, and Linux Mint resource testing before declaring anything ready to ship. Keep graceful fallback until all checks are green.

This staging program introduces no runtime service, polling, shaders or animation.
