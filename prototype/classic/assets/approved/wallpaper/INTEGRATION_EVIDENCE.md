# Approved alpine wallpaper integration evidence

This record covers the Classic wallpaper-default work only. It is not a `main`
merge, not a visual redesign, and not an integration of PR #390's visual-only
commits. No wallpaper bytes were generated or recompressed.

## Source of the exact image

| Field | Exact value |
|---|---|
| Authoritative commit | `f86c17b` |
| Authoritative git blob | `2802e690e1a7d0f16336b90a456dbaea9f5f014d` |
| File | `Canopy_Classic_Master_Wallpaper_1920x1080.png` |
| Bytes | `3,107,170` |
| SHA-256 | `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381` |
| SHA-512 | `81da296eccf0ba1e7f5c238a5c3f51962df863c8a055a180a17ab17223eed682b262681de66cbadb260f2e7ab11829b867eca3edf97b355f5b5fbe6030d954be` |
| Pixels | `1920 x 1080`, PNG 8-bit RGB |

The same blob bytes were installed, without conversion, into both owned paths:

- `prototype/classic/assets/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png`
- `prototype/classic/assets/wallpapers/Canopy_Classic_Master_Wallpaper_1920x1080.png`

The historical `canopy-wave-preview.png` and `blue-current.svg` files were not
modified or deleted. Only one wallpaper `Image` is instantiated at runtime,
with `Image.PreserveAspectCrop`; the second disk copy is a byte-identical
source artifact, not a second decoded image.

## Integration tip and changes

- Base: `06f056ef54081802255b799be00954783208e4b7` (`integration/canopy-classic-20261123`).
- `prototype/classic/Main.qml`: selects the exact master by default, keeps a
  validated `--landscape-wallpaper` override at highest precedence, and does
  not select the blue-wave default. When `--approved-art-dir` is supplied, the
  master is read from that SHA-verified directory; otherwise the exact
  source-tree copy is used. `main.cpp`, `CMakeLists.txt` and `Wallpaper.qml`
  were not changed.
- `tools/check_wallpaper.py`: fail-closed gate (pinned SHA, exact size, PNG
  IHDR dimensions, byte-identical copies, no substitute candidates, default
  selection tokens, exactly one runtime image) with a four-negative selftest.
- `tests/test_check_wallpaper.py`: seven regression tests including negative
  controls for tampering, legacy blue selection, wrong dimensions and generated
  lookalikes.

## Verification actually executed

- `python tools/check_wallpaper.py verify --root .` -> `WALLPAPER_CHECK PASS problems=0`.
- `python tools/check_wallpaper.py selftest` -> green fixture plus four red controls.
- `python -m unittest tests.test_check_wallpaper` -> 7 tests, OK.
- `python -m unittest tests.test_classic_source tests.test_approved_art` -> 23 tests, OK.
- CMake/Ninja Release build of `prototype/classic` with MSYS2 UCRT64 Qt 6.12.0,
  compiler `g++ 16.2.0`, offscreen/software Quick backend.

### Compiled binary

| Field | Exact value |
|---|---|
| Path (scratch) | `C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-wallpaper-build/canopy-classic-spike.exe` |
| SHA-256 | `39fd61d014945f8d041b66c4e4b34d754e6fce942cece7c4b61b14c3bcaa6b3a` |
| Size | `2,123,247` bytes |

### Real Qt captures with the approved wallpaper

Each run used the compiled binary with `--approved-art-dir`, `--self-test-approved`,
`--self-test-size`, `--self-test-screenshot`, and **no** `--landscape-wallpaper`;
every invocation returned rc=0 with no `SELF_TEST_FAIL` and the expected chrome
geometry marker.

| Resolution | Screenshot SHA-256 | Sampled colors | Visual result |
|---|---|---|---|
| 1920x1080 | `58e9416eb1de4c5233b70cd4d736e7a2e64591635c6612f0195e2302341f62bf` | 110 | Alpine lake, mountains, autumn foliage; chrome legible |
| 1200x750 | `e42bd7dadfc13c15009c1a68de01adb0ef857aedadf44f208477948928aac6b7` | 121 | Same artwork, aspect-preserving crop; chrome legible |
| 760x500 | `12231848d9528c036133a73279a076ef0691ea36e14f7c5460789d1fc53ad5d7` | 105 | Same artwork, aspect-preserving crop; chrome legible |

Screenshots are scratch evidence because they contain a live clock and are not
byte-reproducible across runs. The wallpaper file hashes above are stable and
pinned by the gate. Pixel inspection of the 1920x1080 and 760x500 captures
confirms the photographic alpine lake is actually displayed; the top bar, Files
window and dock remain readable.
