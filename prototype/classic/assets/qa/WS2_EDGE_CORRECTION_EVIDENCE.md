# Workstream 2 — bounded Mail / Terminal / Settings Qt edge correction: evidence

**Status: compiled-Qt evidence only. Owner visual approval NOT granted. Linux Mint acceptance: NOT_RUN.**

## Authoritative inputs (unchanged)

| Artifact | SHA-256 |
|---|---|
| Approved wallpaper master (`canopy_approved_assets/wallpaper/master.png`, 3,107,170 bytes, 1920x1080) | `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381` |
| Original icon manifest | `5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737` |
| All eight icon masters | byte-for-byte SHA-locked to the manifest; verified again before each Qt run |

The extracted originals are fully opaque RGBA PNGs. Objective read-only pixel diagnosis
(`ws2_icon_diagnosis.json`, SHA-256 `af9093563a5e7ffd3f60332aaf97a95b817fb996d8d57ad1fce70fd95d00cc59`):

- Terminal: near-black opaque bands at source rows 0-29 and 312-332; top/right edge pixels `(1,0,14)`, `(1,1,20)`, `(0,5,32)`; bright-feature centroid `(201.1,152.6)` against canvas center `(172,166.5)`.
- Settings: near-black bands at rows 0-15 and 328-332; top edge `(2,1,24)`; the previous trim started at row 22, clipping the upper gear rim while retaining lower matte; centroid y `147.3` (high).
- Mail: no exterior black band, but a dark lower gutter from about row 274 and bright-feature centroid y `131.2` against center `166`; the genuine 1920x1080 Qt slot measured 4.28 px high.

## Bounded correction

Only `prototype/classic/RoundedDockIconProvider.cpp` changed (25 insertions, 12 deletions).
`DockTile.qml`, QML geometry, runtime masks, wallpaper, the eight immutable masters and the
manifest are byte-identical. In-memory source crops only:

| Icon | Source trim (L,T,R,B) | 192px-space optical offset |
|---|---|---|
| Browser | unchanged (none) | unchanged `(0,-8)` |
| Files | unchanged `(7,17,15,2)` | unchanged `(-9,-1)` |
| Mail | `(0,6,0,18)` | `(2,9)` |
| Terminal | `(0,18,2,16)` | `(-9,1)` |
| Settings | `(2,14,2,15)` | `(-5,3)` |

Calendar, Photos and Music never enter these maps and keep the exact clean-matte path.
Production renderer version bumped `canopy-five-qt-v2` to `canopy-five-qt-v3` so stale
packs cannot be mistaken for the corrected set.

## Compiled Qt and captures

Toolchain: MSYS2 UCRT64 Qt6, Ninja, `QT_QPA_PLATFORM=offscreen`, platform plugin
`C:/msys64/ucrt64/share/qt6/plugins/platforms`. Both builds completed and both ran
23 `SELF_TEST_PASS` markers at each resolution with exit status 0. The approved alpine
wallpaper passed the binary's embedded SHA check in all six runs.

| Artifact | SHA-256 |
|---|---|
| Baseline binary (detached worktree at `f86c17b`) | `8e066c610caef2b47716dcc8459a840e9653ab8115528e1cf337835c7c292514` |
| Revised binary | `5952828c228315685b02ffa00073d91cac8f2f13b73c42af6ea750205d7740a2` |
| Baseline pack manifest (v2) | `b39b2ebb0203cbf75c6ca96c6918c243bdd1ebfb30b2d6a7622687e784d783d6` |
| Revised pack manifest (v3) | `df0b7166b0a3269d7f99484d5196633193162eba56b334b25a1ea39f9682a360` |
| Baseline capture 760x500 / 1200x750 / 1920x1080 | `5b9ef8a6e993edfb0aa9a253786d8403f89ab3d2f0a5a0b2ae091163614f752f` / `641ae0032d5cc85252825bbd745786da59731cd823b6b6151e12782f1e1d5397` / `d2ea23ef13ee439d8cec2ae38be24b9b716d5681078df4eca3dad1ce4572ae68` |
| Revised capture 760x500 / 1200x750 / 1920x1080 | `af5d3a43152909699945ac6b036d5c0c3f9f3c1bfdc93310f042fc7af1215b48` / `8c065716a8741efc7ba5a73f261011126f24d7489a771355e3f5341eb29784ce` / `bef1299404fa947ddba4bedae1fa06d08fb850c87f1f14082cf14b53f242a6bc` |
| Complete evidence manifest | `4fe913740bc250e6712479a3b63c426ef98856b9c3fc28271fc9b166e447af4e` |

All six PNGs passed `tools/check_screenshot.py` at their exact dimensions. The full
machine-readable manifest (per-icon crop hashes, per-run log hashes, 15 transparency
checks, pack file hashes) is at
`C:/Users/X1/AppData/Local/hermes/cache/scratch/ws2-evidence/ws2_evidence_manifest.json`
with the SHA above.

## Pixel-diff result (genuine Qt frames, same resolutions)

Changed pixels at 760x500 / 1200x750 / 1920x1080: Browser 0/0/0, Files 0/0/0,
Calendar 0/0/0, Photos 0/0/0, Music 0/0/0, Mail 2823, Terminal 2797, Settings 2822.
Unexpected non-icon pixels: 0. Only the bounded live-clock region changed (88/87/88 px).
Frozen-five 62x62 crop hashes at 1920x1080:

- Browser `4f49921e63cacb9b84bc2a31588d51c540703b8d6f725b0d450abe5bcc2e6ecb`
- Files `e7ab68c7686cc24228307d81bc8608596d13f47303e18b0dfd31c4d9a04db738`
- Calendar `30e942103f3f63410b65733d99b2014e78d3bd05ed45027562370dc860d22e68`
- Photos `95f9343b43c187e0410b29b5c194f5190288371891d695d7180ddd8cb595874b`
- Music `a1f75d20256952dab214c49d2ce4c2983ee9997cb888245c9eb6bb36a6c02abc`

The 2x/3x Browser and Files production PNGs are also byte-identical to the v2 pack at
all densities; only Mail, Terminal and Settings pack files changed. All 15 pack PNGs
have zero alpha at all four corners and alpha >= 250 at center.

## Suite delta and resource impact

`python3 -m unittest discover -s tests`: base 393 tests (3 failures, 37 errors),
revised 393 tests (3 failures, 37 errors). Exact FAIL/ERROR name sets are equal
(SHA-256 `ea14a001d9eaca43dd10fb2afee7baf26c4a8cc3417aca37900de8954b2caa8f`).
Logs: base `5ea1ba16b9a5c3c715adcc5bc705b9ce3bd89fbdd64e9f0aa2a1271b72591da8`,
revised `67ce2781a9c38c07da588f1e601e9d0b0fb7e0f7890137df19ced267bd5fb104`.
Targeted icon/pack/manifest contracts: 22 tests OK.

Resource impact: no new timer, thread, shader, effect or per-frame work; the same
one-time cached renderer draws the same 192/384/576 rasters. Real-runtime PSS/CPU:
`NOT_RUN`. Screen-reader behavior: unchanged (no accessibility metadata edited).
Evidence class: `COMPILED_QT_OFFSCREEN` scoped to the Windows UCRT64 host; Mint
acceptance and owner visual approval remain `NOT_RUN` / not granted.
