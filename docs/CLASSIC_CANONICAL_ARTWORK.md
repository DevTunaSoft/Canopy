# CANONICAL: Canopy Classic approved icon artwork + blue wave

**Updated November 20, 2026. Applies to current Classic visual target.**
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

## Wallpaper — updated owner direction (November 20, 2026)

**Latest choice supersedes the old wave:** The owner supplied a reference
showing a detailed snowcapped mountain/lake at sunset, deep pine forest,
golden autumn trees, pink-purple clouds, reflections and foreground stones.
A professionally produced original or appropriately licensed high-resolution
**photographic** landscape with a similar composition is the target. The
supplied UI screenshot is reference art, not a wallpaper file to crop or
redistribute. No exact photographic wallpaper image has been delivered into
this GitHub repository or visually approved yet. Do not call the historical
wave the accepted current background.

`--landscape-wallpaper /absolute/path/to/landscape.png` uses a supplied
local PNG/JPEG with validated image headers, 1920x1080 minimum dimensions,
safe maximum dimensions/pixels/file size, no symlinks and static Qt caching.
With `--approved-art-dir`, eight icon SHA-256 checks remain mandatory;
the legacy wave is **not required** when the new wallpaper flag is supplied.
This preserves exact user-selected icons without coupling them to old art.
Qt CI uses a synthetic color-band fixture for testing only, never as a
design proposal. See `prototype/classic/README.md`.

### Historical blue-wave reference (compatibility only)

The latest user-liked desktop concept used the original saved blue wave
reference file `canopy-wave-preview.png` (1280×720), previously produced
during this project's design work. The manifest records the SHA-256 of this
**actual PNG**. Avoid using the earlier hand-coded SVG `blue-current.svg`
in the approved rendering path; its art differs from this wave reference.

This does not prove the blue wave was the same as an earlier unnamed upload.
Do not claim an earlier upload's identity unless its exact bytes can be checked.
A future explicitly supplied different background is a separate approved
reference update; do not replace the locked image on an assumption.

## Preservation and delivery

The immutable image files are packaged in ChatGPT Library under
`Canopy/Canopy_Classic_Exact_Artwork_Runtime.zip` and also provided as
a conversation download. That ZIP contains `approved-art/icons/*.png`
and `approved-art/wallpaper/canopy-wave-preview.png`.

The **GitHub repository currently stores the manifest + runtime integration
code, NOT the raw approved PNGs**. The GitHub connector cannot publish large
local binary assets as part of normal UTF-8 `update_file` calls. This is an
explicit packaging block, not license to replace the art with generated SVGs.

For a real source checkout, extract the ZIP to a local directory (without
rewriting its images), then run:

```sh
cmake -S prototype/classic -B build/classic -DCMAKE_BUILD_TYPE=Release
cmake --build build/classic --parallel 2
./build/classic/canopy-classic-spike \
  --approved-art-dir /absolute/path/to/approved-art \
  --self-test-approved --self-test-size 1200x750 \
  --self-test-screenshot approved-classic.png
```

The CLI verifies all 8 PNG SHA-256 digests + wave hash **before showing any
window**. Missing, modified, substituted or unsafe assets cause an error.
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
   plus the wave wallpaper in the desired desktop scene.
3. Test screenshots: real compiled Qt images at 760×500, 1200×750, 1920×1080
   and HiDPI, compared against the approved concept at 100% scale.
4. Visual review by the user: typography, light glass material, spacing,
   window chrome, dock size, alignment, and wallpaper/icon presentation.
5. Linux Mint VM desktop integration, real launch actions, user settings,
   accessibility and measured idle memory/CPU/GPU before calling it a shell.

**Never label a generated concept image a running Qt screenshot.**
**Never label legacy engineering screenshots as "approved".**
