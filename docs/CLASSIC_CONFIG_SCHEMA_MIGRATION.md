# Classic config schema versioning and bounded migration sources

Scope: PE-022. Pure host-side source contract only. Owned files are
`canopy_features/settings/config_schema_migration.py`,
`tests/test_config_schema_migration.py` and this document. The existing
`canopy_features/settings/persisted_preferences.py`, its corrupt-config
recovery blobs and all three settings test files are unchanged. No QML,
Qt/C++ source, approved art, manifest, workflow or protected path is edited.
Nothing here compiles Qt, starts a desktop session or claims Linux Mint
acceptance.

## Document versions

| Version | Shape | Status | Source contract |
| --- | --- | --- | --- |
| 0 | flat `{ "reduced_motion": "reduce" }`, no `version` and no `values` wrapper | legacy source only | `SOURCE_CONTRACTS[0]`; one named step `flat_preferences_to_v1` |
| 1 | `{ "version": 1, "values": { ... } }` | current, written by `PersistedPreferences` | `SOURCE_CONTRACTS[1]`; no step |

This is a **settings-file document format**, not a change to
`docs/HOST_EVENT_CONTRACT.md`: no host event topic, payload field or protocol
version is added. Version 1 remains the only version the store writes.

## Bounded source contract

`SourceContract` is an immutable `NamedTuple` pinning, for each source:

* `version`, `shape` (`flat` or `versioned`), `target_version` and one `step`;
* `allowed_keys` (only currently available keys from
  `persisted_preferences.KEYS`) and `required_keys`;
* `max_keys` and `max_bytes`, both no larger than the store's `MAX_KEYS` and
  `MAX_STATE_BYTES`.

`SOURCE_CONTRACTS` and `MIGRATION_STEPS` are `MappingProxyType` snapshots.
Import fails with `RuntimeError` on registry drift (unknown version, backward
or cyclic step, oversized bound, non-available key, or a chain longer than
`MAX_MIGRATION_HOPS = 2`). `migration_plan(version)` returns a finite tuple of
step names; only the registered flat source has a step today.

`migrate_document(raw)` accepts caller-supplied JSON bytes, bytearray or text,
reads at most `MAX_STATE_BYTES` bytes, and returns a new canonical
`{"version": 1, "values": {...}}` document with sorted keys. It is a decision
gate only: the module imports no filesystem, process, socket or temporary-file
API, opens no path and writes nothing. The caller owns persistence.

### Fail-closed inputs

All of the following raise `ConfigSchemaMigrationError` with fixed category
messages; no source bytes enter a message or log:

* future, unknown, negative, boolean (`True` is not version 1), float or string
  versions; explicit `version: 0` wrappers; a `values` wrapper without a
  version; extra top-level fields;
* duplicate JSON object keys at any level, JSON constants, invalid UTF-8,
  lone-surrogate keys or values, huge numeric literals, excessive nesting,
  non-object documents and wrong container types;
* unknown or unavailable preference keys, non-string values, values outside
  the store's pinned domain, nested value objects, and sources over the byte
  or key cap.

A current document is canonicalized rather than mutated in place; an empty
flat source becomes an empty current document. No partial or guessed value is
ever produced from a rejected source.

## Persisted-preferences boundary

The existing store still reads one file at a caller-owned path, quarantines
the exact raw bytes of any rejected document in `preferences.json.corrupt`
(rotated through three bounded snapshots), refuses to overwrite an unreadable
or oversized file, and writes only through its private atomic replace. A
caller that wants to migrate a legacy flat file reads its own bounded bytes,
asks `migrate_document` for a decision, and hands the resulting current
document to that same storage path. Migration never bypasses quarantine:
`migrate_document` returns no file path, performs no write, and offers no
approval for overwriting bytes the store could not inspect. If the source is
corrupt or undecodable, the existing fail-closed/recovery behavior stays in
force.

## Verification (exact pinned base `b3af78fec35caffa7ede16c5dc0e67c0bae4eeac`)

Runner: uv isolated pytest on CPython 3.14.9 / Windows 11 with the worktree on
`PYTHONPATH`. These are host-side `SYNTHETIC` gates, not compiled-runtime or
Mint evidence.

* Base settings triplet, untouched detached worktree:
  `56 passed, 1 skipped, 77 subtests passed in 5.25s`, rc 0. Log SHA-256
  `9741cc9a7da37bda38ce4196cb01826211e764a09b458f2da7505feafd5ae225`.
* RED, new test file copied onto the untouched base: collection error
  `cannot import name 'config_schema_migration' from 'canopy_features.settings'`,
  rc 2. Log SHA-256
  `8c0fedb4efa8f1390a9e7dbe76830972ef64f19968b8fd463e1f5e222fb66b1e`.
* GREEN, original settings triplet unchanged at the feature head:
  `56 passed, 1 skipped, 77 subtests passed in 3.77s`, rc 0. Log SHA-256
  `5575a96e9c18940b25d5a53945c99d9695287be4275c8bdd6635a7b997a10f55`.
  The PE-009 recovery fingerprint `56/1/77` is preserved exactly.
* GREEN, new module tests plus the original triplet:
  `91 passed, 1 skipped, 121 subtests passed in 4.96s`, rc 0. The new file
  contributes 35 tests and 44 subtests. Log SHA-256
  `1f40620bf62277bc98bb72dce5a6a75f1d949f39e9ffbd0f735f1fe929757fba`.
* `python3 tools/check_foundation.py` -> `PASS`, rc 0. Log SHA-256
  `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad`.
  `git diff --check` rc 0; empty log SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
  All artifacts live in
  `scratch/master_directive_20261126/evidence/config_schema_migration/`
  and carry SHA-256 sidecars.

### Resource / evidence note

Measured here: exact test counts, durations, exit codes and log SHA-256s from
bounded in-memory Python gates on the named host. Label: **SYNTHETIC**.
Deliberately not measured: shell-owned PSS/CPU/GPU/wakeups, compiled Qt
behavior, real Mint session behavior and screen-reader behavior — all
**NOT_RUN**. This module makes a bounded, read-only decision; it adds no
service, polling loop, background wakeup or allocation path proportional to
untrusted input. It trades no stability, security, accessibility or approved
visual quality for a minor gain.

Status: draft for review only. No merge into `main`, no visual approval claim.
