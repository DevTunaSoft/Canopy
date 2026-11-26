# Alpha package design: install, uninstall, rollback

**Pin:** `90dd463dc96d70bae00cfe4b2391784a86fb0b12`
**Branch:** `release/package-alpha-90dd463`
**PR base:** `integration/canopy-classic-20261123`
**Compile status:** `COMPILE_NOT_RUN` until PE-002 publishes the exact binary
SHA-256 and build evidence. This document and the scripts never claim a
compiled binary, a verified Mint session or owner visual approval.

## Scope

A reproducible tarball for an **experimental application entry** on Linux
Mint. It is not a session, compositor, display manager, login manager or
complete desktop replacement. It performs no system-wide installation, uses
no root, installs no service, starts no daemon and contacts no network.

The package is built from the exact pin by `tools/alpha_package/build_package.py`.
It contains the two scripts, a package README, license notices, this design
document, `MANIFEST.json` and `CHECKSUMS.sha256`, plus — only with matching
compile evidence — `payload/canopy-classic`.

The runtime controller `tools/alpha_package/alphactl.py` is deliberately
standalone (stdlib only) so an extracted tarball needs no repository checkout.
It keeps the same ownership contract as the existing
`tools/register_classic_preview.py` / `canopy_features/mint/install_recovery_plan.py`
two-file model, but does not import them: the distributable must be
self-contained and must not depend on files outside its own checksum manifest.
A separate, unmerged QA helper exists on another branch
(`tools/qa/classic_preview_package.py`); this workstream neither imports nor
edits that file.

## Determinism and checksums

- Staging requires a path that does **not** exist; the tarball output path
  must not exist. Nothing is overwritten.
- Source bytes are copied verbatim; modes are recorded in the manifest.
- `MANIFEST.json` records schema 1, source commit, build status, payload pin
  and a `{relative path: sha256, size, mode}` file map. Duplicate JSON keys
  are rejected on read.
- `CHECKSUMS.sha256` has one `sha256  relative/path` line per packaged file
  and `MANIFEST.json`. `verify-package` checks both the checksum file and the
  manifest, including exact sizes, and checks modes on POSIX hosts (mode
  comparison is skipped on Windows, where chmod cannot represent 0600/0644).
- Tarball entries are sorted, carry fixed mtime 0, uid/gid 0 and empty
  uname/gname; gzip mtime is 0. Two builds from identical inputs produce the
  same tarball digest. This is a **SYNTHETIC** determinism property, not a
  statement about compiled behavior.

## Compile gate

`build_package.py plan` stages `COMPILE_NOT_RUN`, a null payload and no binary.
`alphactl.py install` refuses that manifest. `build_package.py build` requires
an explicit 64-hex `--binary-sha256` plus an evidence JSON whose `sha256`
matches that pin, whose optional `source_commit` matches the pinned commit,
whose optional `status` is a terminal-success compile status, and whose
binary streams to the same digest. A mismatched or absent evidence file stages
nothing. The evidence digest is recorded as `build.evidence_sha256`.

## Install contract

1. Verify the package checksums and the pinned payload.
2. Require a user-level absolute `home` with no `..`, no symlink components
   and no protected prefix (`/etc`, `/usr`, `/var`, `/opt`, `/boot`, `/proc`,
   `/sys`, `/dev`, `/snap`, `/root`, Windows system roots).
3. `lstat`-snapshot the two owned paths and the two session-entry probe paths.
   Any symlink, non-regular file, unexpected file, oversize file or existing
   state record refuses the install. No unrelated system config is touched.
4. Write a bounded `install-state.json` with the exact pre-install state and
   expected post-install bytes, then create the desktop entry (0644) and
   ownership marker (0600) with `O_EXCL`/`O_NOFOLLOW` where available.
5. Re-snapshot and compare exact bytes, sizes and modes. Any mismatch unwinds
   only the files created in this run.

The desktop entry has no icon and no `Exec` shell metacharacters; quoted or
backslash-containing binary paths are refused. The marker is the existing
`{"schema":1,"sha256":<entry digest>}` format.

## Uninstall and rollback contract

- Uninstall requires an exact match to the recorded post-install state before
  deleting anything. It deletes the desktop entry, then the marker. If marker
  deletion fails, the desktop entry's exact bytes and mode are restored and
  the result is `FAIL` with `rollback_restored`. On success it verifies that
  both owned paths match the original pre-install state and then removes the
  state record. `original_desktop_restored` is reported from that comparison.
- `rollback --target before` reconciles the live state against the recorded
  original: it deletes only a byte-exact file it created, or restores a
  recorded file that is absent. `rollback --target after` re-creates the
  recorded installed state. A modified or unmanaged file produces a refusal,
  never an automatic deletion. Session-entry probes must be absent.
- All mutating commands require explicit `--apply`. Without it they emit a
  bounded JSON plan with `dry_run=true`, `performs_changes=false`,
  `privileged=false`, `session_changes=[]`, `system_paths_written=[]` and
  `native_mint_session_acceptance="NOT_RUN"`.

## Verification performed here

Targeted Python tests live in `tests/test_alpha_package_contract.py` and
`tests/test_alpha_package_build.py`. Results, exact head and SHA-256 sidecars
are recorded under `scratch/master_directive_20261126/evidence/package_alpha`.
ShellCheck was unavailable on this host, so no shell script was introduced
and that check is reported `NOT_RUN`.

## Known limitations

- **COMPILE_NOT_RUN:** no package built in this workstream claims a compiled
  binary; plan-only artifacts cannot be installed.
- Native Linux Mint session, compositor, window manager, focus, wallpaper and
  logout/re-entry behavior: **NOT_RUN**. No guest was contacted.
- Screen-reader behavior, real PSS/RSS, CPU, GPU, wakeups and startup time:
  **NOT_RUN**. Tests exercise bounded JSON/dict logic and small synthetic
  files only (**SYNTHETIC**). No runtime resource tradeoff was made: this
  change adds no service, timer, daemon, binary or visual asset.
- No `.deb`, no apt repository, no system directories, no sudo path, no
  kernel/module or display-manager integration.
- Checksums are integrity checks, not signatures. Provenance and license
  grants are not established; see `NOTICE.md`.
- Qt is not bundled; the target system must supply a compatible runtime.
- Windows chmod cannot represent POSIX 0600/0644; mode checks are skipped on
  Windows. Real mode verification remains a Mint guest task.
- This design does not claim owner visual approval or release readiness; no
  merge to `main` and no protected PR action is performed.
