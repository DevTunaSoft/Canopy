# Canopy Classic — approved master wallpaper

**Approval:** The project owner explicitly selected the exact alpine lake and autumn foliage image on 2026-11-22 and designated it the **Canopy Classic master wallpaper**. It is not a suggestion or a placeholder.

## Canonical image identity

| Field | Exact value |
|---|---|
| Canonical file | `Canopy_Classic_Master_Wallpaper_1920x1080.png` |
| Pixels | `1920 × 1080` |
| Format | `PNG` (RGB) |
| File size | `3,107,170 bytes` |
| SHA-256 of entire file | `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381` |
| Visual | Photographic sunset alpine lake, snowy mountain peaks, turquoise still water, red/orange autumn leaves on the left, golden tree canopy and shoreline on the right |
| Source of truth | Owner-accepted original image, persisted in the owner's ChatGPT Library at `/Canopy/Canopy_Classic_Master_Wallpaper_1920x1080.png` |

**The binary master is stored in the owner's private file Library and not yet part of the public GitHub tree.** A filename, this document, a generated lookalike, or an unrelated image is NOT a substitute for the actual verified 3,107,170-byte PNG. No public URL or GitHub asset download link is asserted.

## Rendering and visual engineering requirements

1. When the verified image is made available to the Linux Mint/Qt project, use **this exact PNG** as the initial/default **Canopy Classic wallpaper**, with a SHA-256 check against the value above before installing or replacing the placeholder.
2. The historical `prototype/classic/assets/approved/wallpaper/canopy-wave-preview.png` is an old CI/comparison fixture, not the approved user-facing wallpaper. Do not call that blue wave master, and do not show it as the eventual desktop default.
3. The existing compiled Qt binary already implements `--landscape-wallpaper PATH`, validates PNG/JPEG size and uses a separate landscape wallpaper property. Use that supported interface for exact-source runtime testing. The current normal Qt preview still defaults to wave without this option. **Do not claim wallpaper integration or full visual acceptance until a real compiled Qt screenshot shows the verified image.**
4. Preserve the exact source PNG: no image regeneration, visual reinterpretation, lossy recompression, added logo, watermarks or colors/brightness edits. Qt may display-scaled or center-cropped by aspect ratio at runtime; never alter the master bytes to do so.
5. Do **not** change or redraw the eight approved dock icon masters, launcher, dock/card geometry, or current optical-alignment work while integrating wallpaper. Wallpaper integration is a distinct visual change.
6. Run actual compiled Qt captures at 1920×1080, 1200×750 and 760×500 on the master image. Verify the screenshot really displays the alpine lake artwork, not merely successful image decoding. Test proper aspect-preserving cover and that the top bar, Files window and dock remain legible.
7. Later support multiple **optional wallpaper choices**. Keep this exact image as the default unless the owner requests a different default. Additional choices must be distinct versioned art files with their own SHA-256 provenance and no rotating wallpaper service or idle CPU overhead unless explicitly requested.

## Artifact and integration status

- [x] Owner approved this exact image as master.
- [x] Exact bytes SHA-256 and dimensions verified.
- [x] Canonical PNG saved to owner's ChatGPT personal Library.
- [ ] Exact binary image present in GitHub/installation package or another verifiable source accessible by the Qt build/installer.
- [ ] Qt application and installer default to the master on ordinary launch.
- [ ] Genuine compiled Qt screenshot evidence across three resolutions.
- [ ] Linux Mint runtime acceptance.

**Work allocation:** ChatGPT owns visual masters, approval and asset selection. Autonomous coding agents may integrate and test approved assets but must not generate replacements, substitute candidates, or pause nonvisual engineering waiting for artwork integration.
