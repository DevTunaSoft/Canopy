# Alpha package design: install, uninstall, rollback

**Original pin:** `90dd463dc96d70bae00cfe4b2391784a86fb0b12`
**Refreshed source commit / PR base tip:**
`c6de24153eef0b58f921a8bffdaeaa8033288a75`
**Branch:** `release/package-alpha-90dd463`
**PR base:** `integration/canopy-classic-20261123`
**Compile status:** `COMPILE_NOT_RUN` until PE-002 publishes the exact binary
SHA-256 and build evidence. The compiled-input label is
`PE002_DIGEST_EVIDENCE_MATCHED`: it claims only that a PE-002-labelled
terminal-success record pins the staged binary digest. This document and the
scripts never claim an independent compile audit, a verified Mint session or
owner visual approval.

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
- Build and plan results echo `package_id` and `source_commit`. Published
  manifest/tarball digests are only reproducible with the exact
  `--package-id` used to produce them; changing the id changes both digests.
  A digest without its package id is not a complete reproduction recipe.

## Compile gate

`build_package.py plan` stages `COMPILE_NOT_RUN`, a null payload and no binary.
`alphactl.py install` refuses that manifest. `build_package.py build` requires
an explicit 64-hex `--binary-sha256` plus an evidence JSON that carries all of:
`id="PE-002"`, a terminal-success `status`, the matching `source_commit` and a
`sha256` equal to that pin. The binary must stream to the same digest. Missing
or mismatched fields stage nothing. The evidence file digest is recorded as
`build.evidence_sha256`, and the manifest status is
`PE002_DIGEST_EVIDENCE_MATCHED`. That label means a self-declared PE-002 record
matched the binary digest; it does **not** claim an independent compile audit
or PE-002 authorship verification.

## Install contract

1. Verify the package checksums and the pinned payload; `apply_install`
   re-reads and re-verifies the exact package bytes immediately before any
   mutation and refuses a manifest, payload or launcher digest that changed
   since the dry-run plan.
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

The desktop entry has no icon. Its `Exec` path is left bare only for the
conservative unquoted character set; any space or Desktop Entry Spec reserved
character triggers a double-quoted field with `\`, `"`, `$` and backtick
backslash-escaped, while `%` field codes are refused. Binary paths with
reserved characters therefore produce a parseable launcher rather than an
unquoted multi-argument `Exec`. The marker is the existing
`{"schema":1,"sha256":<entry digest>}` format.

## Uninstall and rollback contract

- Uninstall requires an exact match to the recorded post-install state before
  deleting anything. State loading refuses any `before` record that is not a
  fully `ABSENT`, so a legacy or tampered claim of a pre-existing owned file
  cannot cause an unrestored deletion. It deletes the desktop entry, then the
  marker. If marker deletion fails, the desktop entry's exact bytes and mode
  are restored and the result is `FAIL` with `rollback_restored`. On success it
  verifies that
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
`tests/test_alpha_package_build.py`. Current results (20 targeted tests), exact
head and SHA-256 sidecars are recorded under
`scratch/master_directive_20261126/evidence/package_findings_fix`; the earlier
author run is under `scratch/master_directive_20261126/evidence/package_alpha`.
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
