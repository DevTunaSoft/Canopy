# Native Plasma rollback evidence

Scope: real runtime proof in the dedicated `Canopy-Test-Plasma6` guest. This document supersedes the inferred-only `PASS_WITH_GAPS` disposition of `rollback_b01_independent_check.md` for the measured behaviors below. It is not a release, visual-acceptance or merge approval.

## Provenance

| Field | Value |
|---|---|
| Owner directive SHA (prefix) | `79e30d79` |
| Base commit | `ec910d7a7275296ecbc8b5e5c459d356205165d1` |
| Evidence | `scratch/native_rollback/native_rollback_runtime_evidence.json` |
| Evidence SHA-256 | `eb3cd8ddf10ca652c36b2a9951e6c6be096b252d57336070ec53701855087d82` |
| Manifest | `scratch/native_rollback/SHA256SUMS.txt` (SHA-256 `f15d51dcbfcc3a19dcaa05ea9837f69674a0dfe1a759abbeec688374cbc08907`) |
| Harness | `scratch/native_rollback/run_native_rollback_proof.py` |
| Runner console | `scratch/native_rollback/run_console.out` |
| VM / transport | `Canopy-Test-Plasma6`, host VBoxManage + SSH to `canopy@127.0.0.1:2223` |
| Run window (UTC) | `2026-11-28T04:11:40Z` .. `2026-11-28T04:15:42Z` |
| Verdict | `PASS` |

The harness stages the unchanged pinned package scripts into the guest. Their SHA-256 values are verified on both host and guest before any write (step C00/C02). No credential content is recorded; the key path is redacted in the evidence.

Pinned binaries used by the real install/rollback scripts: `SHA256SUMS` = `32000906b84ddd653d38a4c2602353ed2012263bac724b7ab8d9b51460435e1e`; binary = `4089251cf6a557d74ca308f3e32f59fea318f62d3285204e9ec7872bcc6b3f14`; wallpaper = `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381`.

## Result

| Metric | Value |
|---|---|
| Ledger steps | 67 |
| PASS steps | 67 |
| HOLD steps | 0 (none) |
| Framebuffer captures | 2 |
| Harness notes | none |

## Gap closure

### N02/N03/N04 config-untouched: direct before/after hashes

The earlier B01 chain had only N01 with a config hash pair; N02/N03/N04 rested on fail-closed abort ordering. Each control now captures both Plasma config hashes and modes immediately before the refusal and immediately after it, before any restoration of the tampered artifact.

#### N01

Direct hash proof: `yes`; equal: `True`.

| Config | Before (SHA-256 / mode) | After (SHA-256 / mode) | Result |
|---|---|---|---|
| `plasma-org.kde.plasma.desktop-appletsrc` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | EQUAL |
| `plasmashellrc` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | EQUAL |

#### N02

Direct hash proof: `yes`; equal: `True`.

| Config | Before (SHA-256 / mode) | After (SHA-256 / mode) | Result |
|---|---|---|---|
| `plasma-org.kde.plasma.desktop-appletsrc` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | EQUAL |
| `plasmashellrc` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | EQUAL |

#### N03

Direct hash proof: `yes`; equal: `True`.

| Config | Before (SHA-256 / mode) | After (SHA-256 / mode) | Result |
|---|---|---|---|
| `plasma-org.kde.plasma.desktop-appletsrc` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | EQUAL |
| `plasmashellrc` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | EQUAL |

#### N04

Direct hash proof: `yes`; equal: `True`.

| Config | Before (SHA-256 / mode) | After (SHA-256 / mode) | Result |
|---|---|---|---|
| `plasma-org.kde.plasma.desktop-appletsrc` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | `fa81ab829aeb54153e1f6e088571b388b7c3c4a597e598e518d383454a793a8c` / `600` | EQUAL |
| `plasmashellrc` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` | EQUAL |

### Personal data preservation

Ten pre-existing user files were SHA-256 hashed at baseline (S00) and again after both full cycles (R17/R18). Count: 10; all equal: `True`.

| User file | Before | After |
|---|---|---|
| `/home/canopy/.config/kwinoutputconfig.json` | `3ac08a9117c6da5a46ae751de32796137cc53a918d105c8dc593c0065f88cc25` | `3ac08a9117c6da5a46ae751de32796137cc53a918d105c8dc593c0065f88cc25` |
| `/home/canopy/g2_g4_copy_hashes.txt` | `91f0551abbeb05c179a920bd06bea4a261f7059045afca83e5f518bcc3d34c07` | `91f0551abbeb05c179a920bd06bea4a261f7059045afca83e5f518bcc3d34c07` |
| `/home/canopy/g2_g4_final_status.txt` | `9798e783184feb8149e6ad99a49ecc09a1e12577048180457bd23fde7003868e` | `9798e783184feb8149e6ad99a49ecc09a1e12577048180457bd23fde7003868e` |
| `/home/canopy/g2_g4_manifest_check.txt` | `8f1689ac622dcc21b63dae27219171c34bced53def91be0385da436a61103db4` | `8f1689ac622dcc21b63dae27219171c34bced53def91be0385da436a61103db4` |
| `/home/canopy/g2_g4_retry_status.txt` | `edabd1fff759674eb037b9d8e5bfb67d8979a0337a0bbf17722ece1f47fd0e1e` | `edabd1fff759674eb037b9d8e5bfb67d8979a0337a0bbf17722ece1f47fd0e1e` |
| `/home/canopy/g2_g4_status.txt` | `541214d833ba936095c902db503073629ead7934fb3f277d0adba26e745a32ed` | `541214d833ba936095c902db503073629ead7934fb3f277d0adba26e745a32ed` |
| `/home/canopy/g2_source_bundle/README.md` | `2de8134b43a26eb05b8d796e14e794023f5130533cf5dfdc6a4fe87244b147dc` | `2de8134b43a26eb05b8d796e14e794023f5130533cf5dfdc6a4fe87244b147dc` |
| `/home/canopy/g3_g4_runtime_package/ACCEPTANCE_CHECKLIST.md` | `074ee060d54973c3877c663e222c043750f8e9afa28258c47931f83acd490e7e` | `074ee060d54973c3877c663e222c043750f8e9afa28258c47931f83acd490e7e` |
| `/home/canopy/g3_g4_runtime_package/README.md` | `33b45e0be02af70bb8e894428f6a1561576a682ac9164642431882ae32c71222` | `33b45e0be02af70bb8e894428f6a1561576a682ac9164642431882ae32c71222` |
| `/home/canopy/g3_g4_runtime_package/config.env` | `418011820f78ee0abf2d358beb337ad76432edec1e798b0ad3f03a991a422c8c` | `418011820f78ee0abf2d358beb337ad76432edec1e798b0ad3f03a991a422c8c` |

### R07 and R15 restoration (byte/mode exact stock fallback)

R07: exact match against stock baseline: `True`.

| Config | Stock baseline (SHA-256 / mode / size) | After R07 |
|---|---|---|
| `plasma-org.kde.plasma.desktop-appletsrc` | `141b7e8889709c41228e1b72841e990180854409e897287cdb284199feefc751` / `600` / `5738` | `141b7e8889709c41228e1b72841e990180854409e897287cdb284199feefc751` / `600` / `5738` |
| `plasmashellrc` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` / `1811` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` / `1811` |

R15: exact match against stock baseline: `True`.

| Config | Stock baseline (SHA-256 / mode / size) | After R15 |
|---|---|---|
| `plasma-org.kde.plasma.desktop-appletsrc` | `141b7e8889709c41228e1b72841e990180854409e897287cdb284199feefc751` / `600` / `5738` | `141b7e8889709c41228e1b72841e990180854409e897287cdb284199feefc751` / `600` / `5738` |
| `plasmashellrc` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` / `1811` | `a7765af1f6a63d919afe49a86b0b0fa531f3b1845f120e035b67962ccc1c2774` / `600` / `1811` |

### Stock fallback with no install manifest

With no manifest, `rollback.sh` must not guess assets or rewrite Plasma config: it removes only the hash-pinned orphan binary and reports that config was not restored. Direct config hashes equal: `True`.

### Upgrade boundary

Step U00 proves install refuses an already-installed host with `already installed (manifest: ...)`; there is no in-place upgrade path. Cycle 2 is therefore an uninstall-then-reinstall (upgrade-equivalent) cycle, not a claim of in-place upgrade support.

## Reproduce

```bash
cd C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-rollback-20261127
python scratch/native_rollback/guest_session_setup.py enable   # real Plasma session
python scratch/native_rollback/run_native_rollback_proof.py
python scratch/native_rollback/build_native_rollback_doc.py
```

The VM must be running (`VBoxManage startvm Canopy-Test-Plasma6 --type headless`). The harness is idempotent: C03 normalizes the guest back to stock before the first install.

## Resource impact and evidence labels

- No production Python/QML/C++/asset file was changed by this task; the deliverable is a runtime harness, evidence JSON and this document.
- Resource measurement of the install/rollback scripts: `NOT_RUN` (no new code path added to the shell; no PSS/CPU claim is made).
- Framebuffer screenshots are REAL captures from the dedicated VM, scoped to install/rollback state, not visual acceptance.
- Screen-reader behavior: `NOT_RUN` (no accessibility or announcement code touched).
- Visual acceptance, CI-on-guest automation, host apt/dpkg install, public release and any main merge: `NOT_RUN`. `release_ready=false`.

