# CANONICAL: Canopy Classic exact icon artwork + current landscape direction

**Updated November 20, 2026. Icon selection is locked; the wallpaper direction has subsequently changed.**
**Status:** Eight app icon choices approved by the user; latest macOS-inspired
desktop concept described as "Looking much better" (directional approval,
not proof the compiled Qt application matches the render).

## Exact eight choices (not moodboard guesses)

The user explicitly supplied the contact sheet
`Canopy_Classic_Eight_Approved_Original_Icons.png`, then asked that **these
exact images** be used. These choices supersede the six-category *moodboard*
lineup in `docs/VISUAL_REFERENCE_PROVENANCE.md`:

| Dock order | App | Original option | Exact PNG from the user sheet |
|:--:|---|:--:|---|
| 1 | Browser | 3 | `Browser_Option_3.png` |
| 2 | Mail | 5 | `Mail_Option_5.png` |
| 3 | Files | 2 | `Files_Option_2.png` |
| 4 | Calendar | 3 | `Calendar_Option_3.png` |
| 5 | Photos | 2 | `Photos_Option_2.png` |
| 6 | Music | 3 | `Music_Option_3.png` |
| 7 | Terminal | 4 | `Terminal_Option_4.png` |
| 8 | Settings | 8 | `Settings_Option_8.png` |

These are actual image **crops of the supplied sheet**: the 345×333(–334)
pixel original source rectangles, without recoloring, illustration,
synthetic replacements, fake vector tracing, or JPEG conversion. The
full SHA-256 of every crop appears in the committed
`prototype/classic/assets/approved/manifest.json`. This manifest locks
*the actual approved pixel data*, not merely labels or application categories.

## Wallpaper

**Current direction (November 20, 2026):** The owner requested a
photographic-quality **alpine lake / autumn trees / snowy peaks / sunset**
landscape similar to the supplied reference screenshot. The prior blue wave
is *superseded as a visual target*; it remains SHA-locked in the historical
artwork manifest and ZIP for byte provenance and compatibility only.
The screenshot contains desktop UI overlays and is **not** itself a clean,
licensed, distributable wallpaper. An original or redistribution-cleared,
standalone high-resolution landscape asset is still required.

Use `--landscape-wallpaper PATH` together with `--approved-art-dir PATH`
for current-direction Qt captures. Do not show synthetic test wallpaper,
the archived blue wave, or flat SVG landscapes as though they fulfill this
current visual direction.

## Preservation and delivery

The immutable image files are packaged in ChatGPT Library under
`Canopy/Canopy_Classic_Exact_Artwork_Runtime.zip` and also provided as
a conversation download. That ZIP contains `approved-art/icons/*.png`
and `approved-art/wallpaper/canopy-wave-preview.png`.

The **GitHub repository currently stores the manifest + runtime integration
code, NOT the raw approved PNGs**. The GitHub connector cannot publish large
local binary assets as part of normal UTF-8 `update_file` calls. This is an
explicit packaging block, not license to replace the art with generated SVGs.

For a real source checkout, install the **unaltered** original ZIP
directly, without a manual unzip or file rearrangement step:

```sh
python tools/install_approved_art_zip.py \
  --archive /absolute/path/to/Canopy_Classic_Exact_Artwork_Runtime.zip \
  --destination /absolute/path/to/approved-art
```

This validates the archive paths and provenance manifest, rejects duplicate,
symlinked, unexpected or tampered contents, then publishes all nine exact
SHA-locked PNGs atomically. An already-correct destination is a no-op; a
modified destination is rejected, never silently overwritten. The ninth
image is the *archived wave reference*, not the current alpine target.

After supplying a **separately cleared** alpine landscape image, run:

```sh
cmake -S prototype/classic -B build/classic -DCMAKE_BUILD_TYPE=Release
cmake --build build/classic --parallel 2
./build/classic/canopy-classic-spike \
  --approved-art-dir /absolute/path/to/approved-art \
  --landscape-wallpaper /absolute/path/to/cleared-alpine-landscape.png \
  --self-test-approved --self-test-size 1200x750 \
  --self-test-screenshot approved-classic.png
```

The CLI verifies all eight PNG SHA-256 digests and validates the selected
landscape image **before showing any window**. Missing, modified, substituted or unsafe assets cause an error.
It cannot silently load the old demo art in this strict mode.
The no-flag code path is the old **unapproved engineering fixture** only;
its screenshots never establish approved look.

Or, if the original images are stored in two separate source locations, run
`python tools/prepare_approved_art.py --icons-dir PATH --wallpaper PATH
--destination OUTPUT`; this copies the same bytes atomically and rejects
any checksum mismatch.

## Release gates (not all passed yet)

1. Exact artwork: preserve PNG source bytes and hashes, don't crop again or
   generate lookalike versions. Do not use the six SVG demo icons for release.
2. Qt runtime: `--self-test-approved` must load **eight** actual app icons
   plus an independently supplied, validated alpine landscape in the desired
   desktop scene. The archived wave is not the current design target.
3. Test screenshots: real compiled Qt images at 760×500, 1200×750, 1920×1080
   and HiDPI, compared against the approved concept at 100% scale.
4. Visual review by the user: typography, light glass material, spacing,
   window chrome, dock size, alignment, and wallpaper/icon presentation.
5. Linux Mint VM desktop integration, real launch actions, user settings,
   accessibility and measured idle memory/CPU/GPU before calling it a shell.

**Never label a generated concept image a running Qt screenshot.**
**Never label legacy engineering screenshots as "approved".**
