# Integration-targeted v3 five-icon port — QA evidence

**Status: compiled-Qt evidence only. Owner visual acceptance NOT granted. Linux Mint acceptance: NOT_RUN. NO MERGE.**

## Port provenance

| Item | SHA |
|---|---|
| Integration base at task start | `06f056ef54081802255b799be00954783208e4b7` |
| Branch base (live integration tip when branched) | `3e287fb2ae77d0e571d98d53f6610bb3b6bd5f0b` |
| Live integration tip re-queried after work | `9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2` (installer-only advance; zero overlap with owned paths) |
| Original renderer correction | `522f292be44e0f8d7edd8d6f4cff1f32700cc42f` |
| Original v3 provenance gate | `c0d983a7f96348be039387a9862aa041566c1167` |
| Minimal infra commit (new) | `abc1f64ba0dd682d34614717615e9bb93fc30be9` |
| Ported renderer correction (cherry-pick, new) | `52f79d032663e678d533e0011f83c287fb850fd3` |
| Ported v3 gate (cherry-pick, new) | `22f914e5ebf99a10a4e4643d59a151a88ae38ac2` |

Only three commits sit on the branch: minimal five-pack renderer/validator infrastructure and the two exact cherry-picks (`-x` trailers retained). None of the 13 rejected visual commits is on the branch. `main.cpp`, `CMakeLists.txt`, `DockTile.qml`, window-activation code, `Main.qml`, all icon masters, wallpaper and dossier docs are byte-identical to the integration tip.

Owned-file byte identity was verified against the proven source commits (LF-normalized content): `RoundedDockIconProvider.cpp`/`.h` and `WS2_EDGE_CORRECTION_EVIDENCE.md` equal `522f292`; `validate_five_production_icons.py` and `test_five_production_pack_version_gate.py` equal `c0d983a`.

## Compile evidence (real MSYS2 UCRT64 Qt6 / Ninja)

- PR tree compiled unchanged with its own integration `CMakeLists.txt`/`main.cpp`: binary SHA-256 `fa5fd1a05cc095eee604d5837db3383aec7b14fd1f7ee22a6ab64cb0430ec880`.
- For genuine five-pack captures only, a scratch harness (never committed, never pushed) used the proven `522f292` `main.cpp`/CMake/QML so the existing export and five-center self-test flags remain available; the owned provider/validator/test bytes are the exact branch bytes. Binary SHA-256 `57080d4e76de65a29d4e4b4dde6fb5993e8cb9a749526147497e0128d9dd25ce`.
- Clean offscreen builds exited 0; all six captures report 23 `SELF_TEST_PASS` markers and exit 0; all six PNGs passed `tools/check_screenshot.py` at their exact dimensions.
- Approved wallpaper master SHA-256 `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381`; original manifest SHA-256 `5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737`; all eight masters SHA-verified.

## Captures and crops

| Resolution | Baseline (v2) | v3 port |
|---|---|---|
| 760x500 | `5609df0caefb625a2546dad130d82d7271ff558b96a39a002e13065720a37144` | `38ad2d87d2ee5004b662778a7cd9759207780f94f7c48e293ca94c5c44717615` |
| 1200x750 | `94591c401347bd4680b2a9be09e6d08a7038d40fff695b79f6ec4c3f264f94c4` | `eae0ea582a9ca36bd4a8c030477f5ad52dbe6dde25a0f24177c96886d1ef9cdf` |
| 1920x1080 | `62517701aeeeaccb198fee37f5812944c2c01fc942fea32d4c3b19ac61a58dee` | `e23a0deaf9dbbe0a513b52a5772f3e06afe48c06144118cef33b006d603c8958` |

Runtime log SHA-256s (base / v3): 760x500 `aee38a2e4f83c13d1afefabc9d1e4b63d784cc8dbe34f8e686ab92d9f4790d65` / `65c6a83863a019bef3c207ebf2021a6f4be237883e79fa2bf064346bfeaf1127`; 1200x750 `03cb2236891a031f5828c8ac65b08b998d28d8270d4a41ca66020a366ff92e2e` / `d29dde80f2b4f923f286b24788ad2a29ceb2983d927a9737192ae20cba6034d1`; 1920x1080 `f9f4881814e814f42646d8bee9f6cab3df7efaa2956262b98491c50cca0239ed` / `1941317432579f498f4f0768407d0cf9dae773d08dec5d613ccc649fe36e587b`.

Frozen-five 62x62 dock crop hashes at 1920x1080 (identical to accepted v3 evidence):

- Browser: `4f49921e63cacb9b84bc2a31588d51c540703b8d6f725b0d450abe5bcc2e6ecb`
- Files: `e7ab68c7686cc24228307d81bc8608596d13f47303e18b0dfd31c4d9a04db738`
- Calendar: `30e942103f3f63410b65733d99b2014e78d3bd05ed45027562370dc860d22e68`
- Photos: `95f9343b43c187e0410b29b5c194f5190288371891d695d7180ddd8cb595874b`
- Music: `a1f75d20256952dab214c49d2ce4c2983ee9997cb888245c9eb6bb36a6c02abc`

Changed three 62x62 crop hashes at 1920x1080: Mail `a1cfc0bb17471ac8faf592d6a988a8444b1f8f83288496643ca63624bf9613be`, Terminal `0a0c7315ee43ae7bbd5c29e294ed546840204a96c0f9e9982b194c8171252c65`, Settings `14104998603607d90f3fae9573a782eff10dcef3a30ef5b7b4b39f73a2ce0a97`.

## Pixel diff (genuine frames)

Changed pixels at 760x500 / 1200x750 / 1920x1080: Browser 0/0/0, Files 0/0/0, Calendar 0/0/0, Photos 0/0/0, Music 0/0/0; Mail 2823, Terminal 2797, Settings 2822 at every size. Unexpected non-icon pixels: 0 at all sizes. Clock-region pixels: 0/0/53. Full machine-readable manifest SHA-256 `ebb0a467a708633390aaf287ae8a73105d326b8b1fb4634ac3b06f88a6516748` at `C:/Users/X1/AppData/Local/hermes/cache/scratch/v3port-evidence/v3port_evidence_manifest.json`.

## Five-pack transparency and provenance

- Baseline v2 pack manifest SHA-256 `b39b2ebb0203cbf75c6ca96c6918c243bdd1ebfb30b2d6a7622687e784d783d6`; v3 port pack manifest SHA-256 `8879e5272bad316f5dcc25e4a42666c9da89ab4472ebfbee7eeac3cf46a704d7` (renderer `canopy-five-qt-v3`, canonical source digest `5aa040dd…`).
- All 15 v3 pack PNG hashes match accepted v3 evidence byte-for-byte; Browser and Files remain byte-identical to v2 at 1x/2x/3x; Mail/Terminal/Settings changed at all densities.
- Validator: `CANOPY_FIVE_PRODUCTION_ASSET_PACK_PASS: 15 SHA-checked PNGs; 3 frozen excluded` (exit 0); report SHA-256 `93ab3380cf33bea461cb9135b1eb4be793b6f28362296e2786d6267dde01a8df`; all 15 rows have four zero-alpha corners and center alpha >= 250.

## Suite and exact checks

`python -m unittest discover -s tests` in a private base worktree pinned to `3e287fb2ae77d0e571d98d53f6610bb3b6bd5f0b` and in the feature worktree: base `Ran 3231 tests in 23.743s` / `OK (skipped=43)`; feature `Ran 3236 tests in 24.790s` / `OK (skipped=43)`. Exact FAIL/ERROR name sets are identical (SHA-256 `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`); the only count change is the five added gate tests. Suite report SHA-256 `c862f386c61801a1bcc830a0ca556adea1581368b2f0368f299099d955267a2a`.

Targeted `tests.test_five_production_pack_version_gate`: 5 tests OK. Direct validator runs: v3 pack PASS (rc 0); stale v1/v2/v3-alpha/unregistered versions rejected by the gate tests.

## Resource / evidence note

Measured: compile-time Qt work and bounded Python validation only. Real-runtime idle PSS/CPU: `NOT_RUN` (no runtime code path added). Timing microbenchmark: `NOT_RUN` (no performance claim). Screen-reader behavior unchanged (no accessibility metadata, QML or announcement code edited). No new timer, thread, shader, effect or per-frame work; the same cached renderer draws the same 192/384/576 rasters. The change cannot trade stability, security, accessibility or approved visuals for a gain: only bounded in-memory source crops and an exact-string provenance gate changed. Evidence class `COMPILED_QT_OFFSCREEN`, scoped to the Windows UCRT64 host; Linux Mint acceptance is `NOT_RUN` and owner visual acceptance is pending. Draft PR only; no merge.
