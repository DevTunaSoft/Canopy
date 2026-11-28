# Native development artifact (2026-11-28)

**One installable development artifact** assembled from the unpinned-by-release,
unprotected integration candidate `integration/native-bundle-candidate-20261128`
head `21c32b61a29f61210fef38c6b9447b49dbfd10bf`. This branch is
`integration/native-dev-artifact-20261128`.

**NO RELEASE.** `NO_RELEASE`, `NO_VISUAL_APPROVAL`, `NO_MERGE`, `NO_APPROVAL`,
`NO_CI_CLAIM`. No protected branch, PR, approval or merge is touched here. The
artifact exists so an independent tester does not have to assemble PRs by hand.
Owner directive SHA-256: `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a` (Rev3, prefix `1fba4b1e`). The previous 2026-11-27 integrated directive pin is `SUPERSEDED_POINT_IN_TIME`.

## Exact pins

| Item | Identity |
| --- | --- |
| Candidate source commit | `21c32b61a29f61210fef38c6b9447b49dbfd10bf` |
| Candidate source tree | `1b962fd2ab9f319409de895765d7b5c5f3261294` |
| Known-good build source | `ec910d7a7275296ecbc8b5e5c459d356205165d1` / tree `3c6110a77e9e34be367a4d11b29c3d6a13138bab` |
| Package | `org.kde.plasma.canopyclassic`, `Plasma/Applet`, `0.1.0-dev-baseline`, Plasma API min `6.0` |
| Compiled binary inside package | `4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32` (2,442,112 bytes) |
| Installable KPackage archive | `ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35` (5,503,210 bytes) |
| Approved wallpaper | `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381` |
| Artifact archive | `canopy-native-dev-artifact-20261128.tar.gz`; exact SHA-256 in `scratch/native_dev_artifact/SHA256SUMS.txt` and `DEV_ARTIFACT.json` |

The source commit/tree SHAs are git object identities; all other values are
SHA-256 content identities. The full per-file content identity of the candidate
tree is embedded as `SOURCE_ID.json` inside the artifact (git blob bytes, LF).

## What is in the one archive

```
.                         archive root = bundle root (flat, no wrapper)
  README.md                 this document, copied verbatim at build time
  ARTIFACT_ID.json          pins, scope, embedded-path list, verdict PASS
  SOURCE_ID.json            SHA-256 of every file in the pinned candidate tree
  SHA256SUMS                exact SHA-256 of every member except itself
  source/prototype/classic/ compiled project source and approved assets
  source/tools/native/      build, template, smoke and artifact tooling
  source/docs/NATIVE_*.md   native contracts and install/rollback evidence docs
  binary/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz
```

The archive root *is* the bundle root; do not add a wrapper directory. The
binary archive root *is* the KPackage root; do not add a wrapper directory.
Only the source paths listed in `ARTIFACT_ID.json` are embedded; `SOURCE_ID.json`
pins the complete candidate tree so a tester can check any other path against
the exact commit.

## Reproduce and check integrity

```bash
WT=C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-dev-artifact-20261128
PYTHONPATH="$WT" python tools/native/artifact/build_dev_artifact.py \
  --worktree "$WT" --out "$WT/scratch/native_dev_artifact"

# independent check of the already built bytes (no rebuild)
PYTHONPATH="$WT" python tools/native/artifact/build_dev_artifact.py \
  --worktree "$WT" --out "$WT/scratch/native_dev_artifact" --verify-only \
  --expected-sha "$(awk '{print $1}' "$WT/scratch/native_dev_artifact/SHA256SUMS.txt")"
```

The builder reads the pinned git objects (never a moving branch), rejects any
binary whose bytes disagree with the prior build manifest, writes no timestamp
into the archive, and packages twice; `archive_rebuild_byte_identical` passes
only when both packagings are byte-for-byte equal. A shallow clone needs
`git fetch --depth=1 origin 21c32b61...` for the pinned objects.

Host-side checks:

```bash
cd "$WT/scratch/native_dev_artifact"
sha256sum -c SHA256SUMS.txt
tar -xzf canopy-native-dev-artifact-20261128.tar.gz -C <check-dir>
cd <check-dir>
sha256sum -c SHA256SUMS
```

## Install (Plasma 6 guest, user scope, no sudo)

Use a desktop session with Plasma 6, `kpackagetool6`,
`plasma-apply-wallpaperimage`, and an active X11/KWin session. Installation is
user-scoped: no system files, no approved asset bytes changed, no VM mutation.

```bash
# 0. outer and inner integrity checks above must pass first
tar -xzf canopy-native-dev-artifact-20261128.tar.gz -C ~/canopy-dev-artifact
B=~/canopy-dev-artifact
cd "$B"
sha256sum -c SHA256SUMS

# 1. extract and check the exact KPackage archive
mkdir -p ~/canopy-dev-package ~/canopy-dev-state
tar -xzf "$B/binary/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz" \
    -C ~/canopy-dev-package
cd ~/canopy-dev-package
sha256sum -c SHA256SUMS                       # 17 members including wallpaper

# 2. install at user scope, then verify
./install.sh \
  "$B/binary/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz" \
  ~/canopy-dev-state
./verify.sh ~/canopy-dev-state
kpackagetool6 --type Plasma/Applet --list | grep org.kde.plasma.canopyclassic
```

`install.sh` snapshots `~/.config/plasma-org.kde.plasma.desktop-appletsrc`
into `<state>/backup/`, checks the approved wallpaper hash, installs with
`kpackagetool6` and records `<state>/installed-config.sha256`. If
`org.kde.plasma.canopyclassic` is already listed, the shipped script uses
`kpackagetool6 --upgrade` on the exact archive (in-place upgrade for this same
package id); on a fresh host it uses `--install`. An in-place upgrade keeps the
config snapshot taken by that install and does not preserve later user edits;
for a different package version/id, a failed upgrade, or any rollback, use the
uninstall-then-install path below. The shipped `uninstall.sh` restores a
snapshot byte-for-byte only while the config still matches
`<state>/installed-config.sha256`; otherwise it preserves the user copy and
reports `UNINSTALL_PASS_USER_CONFIG_PRESERVED`.

## Uninstall

```bash
cd ~/canopy-dev-package
./uninstall.sh ~/canopy-dev-state
kpackagetool6 --type Plasma/Applet --list | grep org.kde.plasma.canopyclassic || echo absent
```

`uninstall.sh` removes the package and restores the snapshotted Plasma config
byte-for-byte **only if** it still matches the install-time hash. If the user
changed the config in the meantime, it is not overwritten: a copy is saved at
`<state>/user-preserved/plasma-org.kde.plasma.desktop-appletsrc` and the script
reports `UNINSTALL_PASS_USER_CONFIG_PRESERVED`. An in-place `--upgrade` is
supported only for the same package id; a version change uses
uninstall-then-install, and rollback always starts from an uninstall.

## Rollback to known-good

Known-good means the pinned `0.1.0-dev-baseline` binary at SHA-256
`ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35`, built
from `ec910d7a7275` (evidence: `docs/NATIVE_BUILD_BASELINE.md` and
`docs/NATIVE_ROLLBACK.md` in this branch).

1. Stop evaluation of the current package: run `./uninstall.sh <state>` above;
   confirm the package is absent.
2. If the config was preserved (not restored), decide explicitly: keep the
   user copy, or copy `<state>/backup/plasma-org.kde.plasma.desktop-appletsrc`
   back only if the user accepts losing later edits. Never force-overwrite a
   changed config.
3. Reinstall the exact pinned archive from this artifact's `binary/` directory
   with the install commands above and re-run `./verify.sh <state>`. The hashes
   in the embedded `SHA256SUMS` fail closed on any substituted binary.
4. Source-level rollback: `git -C <worktree> checkout 21c32b61` for the candidate
   tree, or `ec910d7a7275` for the known-good baseline; this artifact branch is
   never merged or promoted. No VM snapshot is created or reverted by the
   artifact itself.

Real guest proof for the exact bytes shipped here:
`scratch/native_dev_artifact/SHIPPED_ROLLBACK_PROOF.json` records **24/24 PASS**
steps on `Canopy-Test-Plasma6` (`REAL_GUEST_SCOPED`): fresh install,
`verify.sh`, in-place `--upgrade` of the same package id, uninstall with
byte-for-byte config restoration, personal-file preservation, reinstall and
cleanup. It pins `install.sh` = `a4f7ca9ca8fd6a2d4e0a68798b97bacc6a14806553f9829f591640f06c7ff5c2`,
`uninstall.sh` = `94324c5eb7708fa884fc9f3c392ece6c0692b20d5246107ab922b5a61d03c9dc`,
`verify.sh` = `ffa210cd22807db08dfbb7faafd21ef129eb5cca4d928f86f67c496119b7bb61`,
compiled binary = `4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32`
and KPackage archive = `ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35`.
The earlier 67/67 proof in `docs/NATIVE_ROLLBACK.md` is
`SUPERSEDED_POINT_IN_TIME`: it measured a different script/binary identity and
does not prove this bundle. Guest wallpaper-D-Bus recovery was required before
the run and is recorded as a scoped guest-session precondition, not a product
change. Visual acceptance, CI-on-guest automation, approval, merge and release
remain `NOT_RUN` / `NO_RELEASE`.

## Smoke checklist

Record each line PASS / FAIL / NOT_RUN with the exact SHA-256 and UTC time in
the tester's own log; a checkbox is not evidence.

- [ ] `sha256sum -c SHA256SUMS.txt` at the artifact root: PASS.
- [ ] Extract once; `sha256sum -c SHA256SUMS` inside the bundle: PASS.
- [ ] `ARTIFACT_ID.json` scope begins `DEVELOPMENT_ARTIFACT_ONLY` and verdict is `PASS`.
- [ ] Embedded KPackage archive SHA-256 equals `ec9e44cf…ece35`; inner 17-member `SHA256SUMS` PASS.
- [ ] Approved wallpaper SHA-256 equals `8c6cab50…01381` before and after install.
- [ ] One active Plasma X11 user session, exactly one `kwin_x11`, at least one `plasmashell`, no second compositor.
- [ ] `kpackagetool6 --type Plasma/Applet --install` of the exact archive succeeds; `--show` metadata identity OK.
- [ ] In-place `--upgrade` of the same package id succeeds; rollback starts with `uninstall.sh`.
- [ ] Compiled binary launched in that session; a live X11 window is observed.
- [ ] Wallpaper path present in the Plasma image-wallpaper config group; real desktop capture recorded (functional render only).
- [ ] `./verify.sh <state>` prints `VERIFY_PASS`.
- [ ] `./uninstall.sh <state>` removes the package; list shows `absent`.
- [ ] Config restored byte-for-byte, or explicitly preserved with a saved user copy.
- [ ] Any FAIL is recorded with the exact step and artifact SHA; no silent retry with a different binary.

Explicitly not claimed here: CI check green, automatic CI-on-guest, final visual
acceptance, protected-branch merge, public release (`NOT_RUN` / `NO_RELEASE`).

## Gate status

| Gate | Status |
| --- | --- |
| Candidate commit/tree pinned from git objects | PASS |
| Full-tree `SOURCE_ID.json` content identity | PASS |
| Embedded binary SHA/size and prior manifest pin agreement | PASS |
| Deterministic bundle: two byte-identical packagings | PASS (`SYNTHETIC`) |
| Inner and outer `SHA256SUMS` verified from current bytes | PASS |
| Real Plasma guest install/rollback at exact shipped script/binary hashes | PASS (24/24, `REAL_GUEST_SCOPED`; `SHIPPED_ROLLBACK_PROOF.json`) |
| CI, visual acceptance, merge, approval, release | NOT_RUN / NO_RELEASE |

No approved icon, wallpaper, QML or C++ source was redesigned or modified by
this artifact task. Screen-reader behavior: `NOT_RUN`. Resource measurement:
`NOT_RUN` (no new runtime code path). **No release claim.**
