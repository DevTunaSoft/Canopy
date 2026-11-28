# Canopy Classic — native Plasma 6 development baseline (M1/M6)

**Scope:** installable *development baseline* only. This document does not claim
a release, owner visual approval, CI acceptance, a merge or a PR approval. No
approved artwork was redesigned, resampled or regenerated; assets were copied
byte-for-byte and checked by SHA-256 before and after use.

## Exact pins

| Item | Identity |
|---|---|
| Integration base commit | `ec910d7a7275296ecbc8b5e5c459d356205165d1` |
| Integration base tree | `3c6110a77e9e34be367a4d11b29c3d6a13138bab` |
| Branch | `product/native-build-baseline-20261127` |
| Package | `org.kde.plasma.canopyclassic`, `Plasma/Applet`, `0.1.0-dev-baseline`, Plasma API minimum `6.0` |
| Approved wallpaper (SHA-256) | `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381` |
| Built binary (SHA-256) | `4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32` |
| Deterministic archive (SHA-256) | `ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35` |
| Archive size | 5,502,696 bytes |
| Source archive (SHA-256) | `70539d8e89d1cdcc8c6ca825ce2199bc43872c0dc5f1e439625d85545ef36a8c` |
| Executed run | `2026-11-28T05:00:30Z` – `2026-11-28T05:03:52Z`, verdict `PASS` |

The complete evidence set, its own `SHA256SUMS` and the build manifest are in
`scratch/native_build_baseline/`. Key evidence SHAs: `build/MANIFEST.json`
`4436a80aa8c3b3f16ad4764adbb5017da277b4ba3333e401f401ea91c764395b`;
`SMOKE_RESULT.json`
`699aeba440834d396a005dc42c930c8d51de0b4023f15d8db824d2715b8ea20a`;
real desktop capture `815bd39e3c68736cee974bfc8ad196d27ea5cc45bde9b0a9dd6cb2c97ff730a6`
(1920x1080, proof of a real render only).

## What was executed

1. Host driver `tools/native/smoke_test.py` verified the pinned git commit and
   tree, exported the exact base with `git archive`, overlaid only
   `tools/native/**`, and copied it to the existing reference VM over the
   pre-existing scratch SSH key. The VM was already running and shared; the
   driver did not start, stop, save, revert or snapshot it.
2. Guest `tools/native/build_baseline.py` verified `SOURCE_ID.json` (all 760
   source files), the eight approved icon hashes, the approved wallpaper hash
   and the untouched legacy wave reference, then compiled the real Classic
   target with CMake 4.2.3 / Ninja 1.13.2 / Qt 6 (`SOURCE_DATE_EPOCH=0`).
3. The tool staged the KPackage (metadata, minimal KF6 applet QML, compiled
   binary, approved manifest/icons/wallpapers, install/verify/uninstall
   scripts, `SHA256SUMS`) and packaged it twice. Both packagings produced the
   byte-identical archive SHA above (sorted POSIX members, mtime 0, uid/gid 0,
   empty uname/gname, GNU tar, gzip filename empty and mtime 0).
4. Guest `tools/native/guest_smoke.sh` verified a real, active Plasma X11 user
   session (session 65, `Type=x11`, `Class=user`, `Active=yes`), exactly one
   `kwin_x11`, at least one `plasmashell`, no second compositor, then installed
   the exact archive at user scope with `kpackagetool6`, applied the approved
   wallpaper with `plasma-apply-wallpaperimage`, persisted the exact path in the
   existing Plasma image-wallpaper KConfig group (the tool's on-disk sync is
   intermittent in this guest), verified the installed package metadata and
   the config path, launched the compiled binary in that session and confirmed
   a live X11 window plus real 1920x1080 desktop captures.
5. The smoke test removed the package and restored the stock Plasma config
   byte-for-byte. `baseline_absent_after_uninstall` is `PASS`.

### Reproduce (host)

```bash
WT=C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-build-baseline-20261127
KEY=C:/Users/X1/AppData/Local/hermes/cache/scratch/g1_ubuntu_evidence/ssh/g1_ed25519
TREE=$(git -C "$WT" rev-parse ec910d7a^{tree})
PYTHONPATH="$WT" python3 -m unittest discover -s "$WT/tools/native/tests" -p 'test_*.py' -v
PYTHONPATH="$WT" python3 "$WT/tools/native/smoke_test.py" \
  --worktree "$WT" --evidence "$WT/scratch/native_build_baseline" \
  --ssh-key "$KEY" --tree-sha "$TREE"
```

The helper unit tests (8 tests) cover canonical SHA handling, duplicate-key
rejection in `SHA256SUMS`, deterministic tar bytes, symlink rejection and
approved-icon hash negative controls; all passed before the executed run.

### Build artifact verification

```bash
cd <worktree>/scratch/native_build_baseline
sha256sum -c SHA256SUMS
cd build
sha256sum -c SHA256SUMS
```

## Install / verify / uninstall (owner, Plasma 6 guest)

The archive root *is* the package root; do not add a wrapper directory.

```bash
# stage the exact archive; verify its SHA-256 first
sha256sum org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz
mkdir -p ~/canopy-baseline-state
tar -xzf org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz -C ~/canopy-baseline

cd ~/canopy-baseline
sha256sum -c SHA256SUMS                       # 17 files, including the wallpaper
./install.sh <path-to-archive.tar.gz> ~/canopy-baseline-state
./verify.sh ~/canopy-baseline-state
kpackagetool6 --type Plasma/Applet --list | grep org.kde.plasma.canopyclassic

# restore stock Plasma (config restored only if unchanged since install)
./uninstall.sh ~/canopy-baseline-state
kpackagetool6 --type Plasma/Applet --list | grep org.kde.plasma.canopyclassic || echo absent
```

`install.sh` verifies `SHA256SUMS` and the wallpaper hash, snapshots
`~/.config/plasma-org.kde.plasma.desktop-appletsrc`, installs at user scope
(no `sudo`, no system files), and applies the approved wallpaper. `uninstall.sh`
removes the package; if the config differs from the install snapshot it leaves
the user's copy untouched and saves it under `<state>/user-preserved/`. All
paths are user-scoped; no user files or settings are deleted.

## Status of every gate

| Gate | Status |
|---|---|
| Source commit/tree pin and byte-identical source inventory | PASS |
| Approved eight icons, approved wallpaper and legacy wave asset hashes | PASS |
| Real CMake/Ninja compile of the Classic C++ target | PASS |
| Deterministic package (two byte-identical packagings) | PASS |
| Archive SHA-256 copy-back from guest | PASS |
| VM available over existing SSH key; shared VM left untouched | PASS |
| Real Plasma X11 user session, one KWin, one shell, no second compositor | PASS |
| KPackage install, installed metadata, approved wallpaper config | PASS |
| Compiled binary launch with live X11 window in that session | PASS |
| Real 1920x1080 desktop captures (functional render only) | PASS |
| Uninstall and byte-for-byte stock config restoration | PASS |
| FAIL in final executed set | none |
| BLOCKED in final executed set | none |
| Full `--self-test-approved` fidelity suite | NOT_RUN (separate gate) |
| CI check runs / merge / PR approval | NOT_RUN (draft PR only) |
| Owner visual acceptance and release approval | NOT_RUN / pending |

An earlier exploratory run of the full fidelity self-test at this base emitted
`SELF_TEST_FAIL: Files folder grid clipped or unbalanced`; that run was
superseded by the runtime-launch smoke gate and is not part of the final PASS
evidence. No visual acceptance is inferred from any screenshot.

**No release claim.** This is a development baseline for review only; the
protected branch requires a distinct human approval and this work neither
merges nor self-approves anything.
