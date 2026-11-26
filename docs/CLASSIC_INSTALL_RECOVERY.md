# Classic user-level install, uninstall and recovery (offline planner)

**Status:** read-only planner and exact-state verifier. It writes nothing,
uses no root, launches no process and contacts no guest. Native Linux Mint
session acceptance is **NOT_RUN**; no dry-run result may be reported as a real
installation, a working session or a completed recovery.

Issue #107 remains open: its acceptance gate requires a real Mint
session/compositor decision and guest evidence, neither of which is supplied
by this document or its tests.

## Scope and owned files

The real installer is `tools/register_classic_preview.py`. It manages exactly
two user files under `XDG_DATA_HOME` (default `~/.local/share`):

| Role | Path |
|---|---|
| Desktop entry | `$XDG_DATA_HOME/applications/org.canopy.ClassicPreview.desktop` |
| Ownership marker | `$XDG_DATA_HOME/canopy/classic-preview/ownership.json` |

The planner is `canopy_features/mint/install_recovery_plan.py`. It reuses the
installer's paths, pure entry builder and ownership hash; it never imports or
executes the compiled Qt binary.

## Commands

From a repository checkout, all commands are read-only:

```sh
# Exact current state (bytes hashed, never followed through a symlink)
python3 -m canopy_features.mint.install_recovery_plan \
  --home /absolute/user/data/home --action snapshot

# Bounded dry-runs; no directory, file or session is changed
python3 -m canopy_features.mint.install_recovery_plan \
  --home /absolute/user/data/home --action install \
  --binary /absolute/path/to/canopy-classic
python3 -m canopy_features.mint.install_recovery_plan \
  --home /absolute/user/data/home --action uninstall
python3 -m canopy_features.mint.install_recovery_plan \
  --home /absolute/user/data/home --action recover

# Verify an observed state against a saved plan
python3 -m canopy_features.mint.install_recovery_plan \
  --home /absolute/user/data/home --action verify --plan /absolute/plan.json
```

The install tool exposes the same dry-run gate:

```sh
python3 tools/register_classic_preview.py install --dry-run --binary /absolute/canopy-classic
python3 tools/register_classic_preview.py uninstall --dry-run
python3 tools/register_classic_preview.py verify-plan --plan /absolute/plan.json
```

Each plan carries `dry_run=true`, `performs_changes=false`, `privileged=false`,
`session_changes=[]`, `system_paths_written=[]`, and
`native_mint_session_acceptance="NOT_RUN"`. A plan whose claims contradict
those values is rejected before any verdict is returned.

## Exact-state record

A snapshot records, for both owned paths:

- path kind (`ABSENT`, `REGULAR_FILE`, `SYMLINK`, `OTHER`, `OVERSIZE`,
  `UNREADABLE`);
- exact size and mode as observed with `lstat` (symlinks are never followed);
- SHA-256 and bounded base64 of the exact bytes of regular files;
- the ownership marker digest cross-checked against the desktop-entry bytes.

Limits are 8192 bytes for the desktop entry, 4096 bytes for the marker,
65536 bytes for a plan file and at most eight plan steps. Duplicate JSON keys
in a plan file are rejected; a second `dry_run` or `approval` key cannot erase
a safety claim. Paths with control characters, `..`, symlinked components, or
system-owned prefixes (`/etc`, `/usr`, `/var`, `C:\Windows`, `C:\Program Files`,
and similar) fail closed with `RecoveryPlanError`.

The planner also probes user-level `$XDG_DATA_HOME`-relative
`.config/autostart` and `.local/share/xsessions` names matching the managed
desktop-entry ID. Any such entry is an unexpected session change and makes the
snapshot unsafe even when it is a well-formed file.

## Uninstall and bounded rollback

An uninstall plan is produced only when the live state is `INSTALLED` and the
entry bytes match the marker. Its steps delete only the two owned files, in
the real installer's order (desktop entry, then marker). If the marker deletion
fails, the real installer restores the desktop entry's exact recorded bytes
and mode; the rollback is one file, at most 8192 bytes. A modified or
unmanaged entry produces no deletion step: `auto_action_allowed=false` and
`NEEDS_MANUAL_REVIEW`, never a silent cleanup.

Directory creation and removal are deliberately out of scope: directories may
contain unrelated user files and are retained.

## Verdicts

- `PASS` — observed state matches the plan's expected exact bytes and status.
- `FAIL` — corruption, missing/overwritten files, unexpected paths, symlinks,
  partial rollback, or a plan with unsafe claims.
- `NEEDS_MANUAL_REVIEW` — a modified or unmanaged entry was preserved.

A partial rollback is detectable: when the desktop entry is restored but the
marker remains absent, verification returns `FAIL` with
`status_mismatch` and `kind_mismatch:desktop`, not `PASS`.

## Negative controls (offline tests)

`tests/test_mint_install_recovery_plan.py` and
`tests/test_register_classic_preview.py` cover corrupted entry bytes, corrupt
or duplicate-key plans, symlinked binary parents and symlinked entries,
unexpected autostart paths, oversized entries, missing/nonexecutable binaries,
wrong types, protected system homes, uninstall refusal on modified entries,
partial rollback, and no-write/no-execution assertions. Passing these tests is
evidence of offline planning only.

## Resource and evidence note

- Measured: nothing at runtime. No compiled shell, guest or desktop session
  was started by this change. The offline unit tests exercise bounded pure
  Python dictionaries and at most 8 KiB byte snapshots (`SYNTHETIC`).
- Not measured: guest PSS/RSS, CPU, GPU, wakeups, startup time and screen-reader
  behavior — all **NOT_RUN**. No Mint acceptance is claimed.
- This change trades no stability, security, accessibility or approved visual
  quality for performance: it adds no service, timer, process, binary or
  visual asset. The desktop entry text and managed paths are unchanged for a
  real install.

## Next acceptance step (not performed here)

Boot a disposable Linux Mint Cinnamon guest from a snapshot, compile the
pinned source, run the real `install`/`uninstall` commands as a regular user,
verify exact restoration of the original Cinnamon session, and record release,
binary SHA-256, logs and resource measurements. Until that guest evidence
exists, native Mint session acceptance stays **NOT_RUN**.
