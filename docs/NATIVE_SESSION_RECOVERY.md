# M4 native session persistence and crash recovery

Scope: product milestone M4 (deployment and recovery), owner directive SHA
`79e30d79`, cap 8. Base `ec910d7a7275296ecbc8b5e5c459d356205165d1`. Owned
paths only:

- `canopy_features/reliability/session_lifecycle_snapshot.py`
- `canopy_features/reliability/startup_checkpoints.py`
- `canopy_features/settings/persisted_preferences.py`
- `canopy_features/settings/config_schema_migration.py`
- `docs/NATIVE_SESSION_RECOVERY.md`
- `scratch/native_session/**`

No Shell Pack switching path, visual asset, QML, C++ workflow, approval or
merge is touched. No merge or self-approval is performed by this change.

## What changed

`PersistedPreferences._read()` now routes a non-empty flat document (schema 0
in `config_schema_migration.SOURCE_CONTRACTS`) through the registered
`flat_preferences_to_v1` migration decision. The migration module is imported
lazily to avoid its import-time dependency on the store. The store still owns
the only write: a migrated value is in memory immediately, and the exact raw
legacy bytes are preserved in the existing bounded `*.corrupt` quarantine
rotation before the first successful `set()` writes the versioned document.
A corrupt, duplicate-keyed, unreadable or oversized file is still refused or
discarded under the prior fail-closed contract and is never overwritten.

Before this change a flat legacy settings file was rejected as corrupt: the
value did not survive a logout/restart in the in-memory view, and its bytes
were only retained after a later write. Now the value survives a fresh-process
restart both before and after that write, with the original bytes retained.

`startup_checkpoints.py` and `session_lifecycle_snapshot.py` are unchanged.
Their exact-tip contracts are used as evidence: a partial durable startup
yields a persisted `ROLLBACK` decision with `safe_to_start=False` and reversed
unwind order; a corrupted journal yields `FAIL_CLOSED` without overwriting the
raw bytes; a locked session snapshot is `BLOCKED` with
`acceptance=NOT_ESTABLISHED` and `event_observation=NOT_PERFORMED`.

## Verification

Host: Windows 11, CPython 3.14.9, isolated worktree at the base tip. Guest:
running `Canopy-Test-Plasma6` (UUID `3aecd840-4dd6-4481-913f-64a289da406d`),
Ubuntu 26.04 LTS, X11 Plasma with one `kwin_x11` and `plasmashell`, CPython
3.14.4, reached with the pre-existing local SSH key and no new credential.
The harness `scratch/native_session/verify_native_session_recovery.py` is the
same file on both hosts (SHA-256
`bc3e584313acdeadc7322e32c5f503741da27198d99753cc64cfa4e4ee7dda74`, recorded
in `guest_preflight.txt`). Each mode runs in a separate Python process.

Commands (host, from worktree root):

```
PYTHONPATH=. python -m unittest tests.test_c100_settings_persisted_preferences \
  tests.test_config_schema_migration \
  tests.test_c100_reliability_startup_checkpoints \
  tests.test_c100_reliability_session_lifecycle_snapshot \
  tests.test_c100_settings_persistence_isolation
PYTHONPATH=. python scratch/native_session/verify_native_session_recovery.py \
  write /tmp-state/profile
PYTHONPATH=. python scratch/native_session/verify_native_session_recovery.py \
  read /tmp-state/profile --expected reduce
```

The same harness modes `legacy_read`, `legacy_commit`, `crash`,
`crash_corrupt`, `safe_state` and `probe` were copied into the guest under
`/home/canopy/native_session_m4_verify` and run as fresh guest processes over
SSH. Guest staging and all guest state directories were removed afterwards.

Results:

- Host unit gate: `Ran 120 tests`, `OK (skipped=1)`, rc 0.
- Fresh-process settings restart, host and guest: value `reduce` before and
  after, state SHA-256 `e6e77bb45c755098a54b63ffe1959acc82f3706be9cf205befe66e2e839f439f`
  on both hosts. This is the same durable bytes read by a new process.
- Flat legacy settings, host and guest: `legacy_read` returns `reduce` with the
  source still byte-identical (SHA-256
  `aea70a8175c83b30442d8b04bd3607dd9d50f014a502a28b97e1d32dbb2e66c3`);
  `legacy_commit` writes the current document (SHA-256
  `be7ff52c975ef97b0bd2a9d935fe51d6e9ee324159eda36eba42aa0ac4eb39d3`) and the
  quarantine copy equals the original flat bytes. A fresh read after the write
  returns `full`: no settings bytes are lost in either direction.
- Crash mid-startup, host and guest: `ROLLBACK`, `completed=(dock, menu)`,
  `unwind=(menu, dock)`, `safe_to_start=false`; a second fresh `recover()`
  returns the identical decision and leaves the durable state byte-identical
  (SHA-256 `3fffa016b527754a8ed0ff638c3fe44bcf29d411b821bb126351ddd7d562caed`).
- Corrupt journal, host and guest: `FAIL_CLOSED`, `safe_to_start=false`, raw
  bytes preserved (SHA-256
  `1e5499861fb206d4c804c1c842d2503bf7fe43c007801fdc1a804b349422f51c`).
- Safe state on both hosts: recovery decision `ROLLBACK` with
  `safe_to_start=false`, session snapshot `BLOCKED`,
  `acceptance=NOT_ESTABLISHED`, `event_observation=NOT_PERFORMED`.
- `git diff --check` and `python tools/check_foundation.py` at the final head
  are recorded in the PR body, not inferred from the base run.

Evidence files and their SHA-256 digests are listed in
`scratch/native_session/evidence/SHA256SUMS.txt`; `sha256sum -c SHA256SUMS.txt`
passes from that directory. Raw files: `host_unit.log`, `host_harness.jsonl`,
`guest_preflight.txt`, `guest_harness.jsonl`, `guest_session_blocker.txt`.

### Evidence boundary

- **NATIVE_RUNTIME**: the harness imported and executed the owned modules in a
  fresh Python process on the running Plasma guest; the guest was an active
  X11 Plasma session with one KWin and `plasmashell`.
- **SYNTHETIC**: each fresh process is a scoped restart model, and the
  crash/checkpoint states are synthetic files in a caller-owned temporary
  directory. No desktop session was terminated or relaunched.
- **NOT_RUN — actual Plasma logout/login cycle**: at
  `2026-11-28T06:20:15Z` the active seat0 session 65 was being driven by
  another worker's processes (`bash` PID 54982 running `xdotool`/`scrot`,
  `xdotool` PID 58924); see `guest_session_blocker.txt`. Terminating that
  session would disrupt concurrent in-guest work on a shared VM, so no
  `loginctl terminate-session`, SDDM relogin or compositor restart was issued.
  A full logout/login confirmation of these files is therefore explicitly
  `NOT_RUN`, not a PASS and not a product failure.
- **NOT_RUN**: real package install/upgrade cycle, personal desktop data,
  compiled Qt behavior, final visual acceptance and screen-reader behavior.
  The fresh-process byte identity and quarantine equality are scoped proof of
  no data loss for the tested settings and checkpoint files only.

## Resource / evidence note

Measured here: exact test counts, exit codes, file hashes and repeated-decision
identity from bounded host/guest Python gates. Label: **SYNTHETIC** for the
process-restart model, **NATIVE_RUNTIME** for execution on the live Plasma
guest. Deliberately not measured: shell-owned PSS/CPU/GPU/wakeups, full
logout/login, compiled Qt rendering and screen-reader behavior — all
**NOT_RUN**. The change adds one bounded lazy import on the legacy read path,
one in-memory canonicalization of at most 4096 bytes and no service, polling,
background thread or allocation path proportional to untrusted input. It
trades no stability, security, accessibility or approved visual quality for a
minor gain.

Status: draft for review. No merge, no self-approval, no visual approval claim.
