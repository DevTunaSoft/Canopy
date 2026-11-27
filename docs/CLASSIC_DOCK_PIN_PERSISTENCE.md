# Classic dock pin persistence — host-side source contract

Scope: one new pure module, `canopy_features/dock/dock_pin_persistence.py`,
one targeted test file, `tests/test_c100_dock_pin_persistence.py`, and this
contract note. No QML, artwork, icon, wallpaper, dock geometry, typography or
colour file is edited. Existing settings and pin-state modules are left
byte-identical, so this change does not collide with concurrent settings work.

## What is stored

`DockPinStore` persists the ordered identifiers already owned by
`canopy_features.dock.dock_pinned_items` in one canonical file:

```
{"items":["terminal","nemo","files"],"version":1}
```

* `state_path_for_user(root, user)` returns
  `<trusted-root>/users/<user>/dock_pins.json`; `user` is one lowercase
  profile component (the same conservative pattern used by the settings
  store). `DockPinStore.for_user(root, user)` binds a store to that profile.
* `root` is mandatory. The existing
  `canopy_features.security.path_jail_checks` contract canonicalizes root and
  candidate, rejects traversal and absolute escapes, and each read/write
  re-checks the jail and refuses symlinked components.
* Nothing is written at import or in the constructor. `pin`, `unpin` and
  `move` write through a `0o600` temporary file and an atomic replace in a
  `0o700` parent; a failed write restores the in-memory order and leaves the
  durable file byte-identical.

## Restart and corrupt-config recovery

A fresh instance over the same path is the restart boundary: it re-reads the
state file and returns the same tuple order. `unpin` followed by a fresh read
stays removed; a re-pin appends at the end; `move` persists a clamped
reorder.

A missing file starts empty with status `ABSENT`. Malformed JSON, invalid
UTF-8, a duplicate JSON key, a non-object root, an unknown field, a bad
version (including `true`), a non-list order, duplicate/unknown/invalid or
unencodable identifiers, oversized state and JSON constants all discard the
whole document with status `CORRUPT`. Corrupt bytes are not modified by a
read; the next successful user action replaces them with clean ordered state.
Hostile identifier types raise `DockPinPersistenceError` before any write.

## Verification (exact commands and evidence)

Base: `integration/canopy-classic-20261123` at
`90dd463dc96d70bae00cfe4b2391784a86fb0b12`; private worktree
`C:/Users/X1/AppData/Local/hermes/cache/scratch/pe004-dock-pin`, branch
`fix/dock-pin-persist-90dd463`. Runner: uv isolated pytest, repository on
`PYTHONPATH` (`PYTHONPATH=. uv run --no-project pytest ...`).

* RED, new test file copied into a separate untouched detached worktree at
  the exact base SHA: `1 error during collection`, rc=2 —
  `ImportError: cannot import name 'dock_pin_persistence'`. The RED log,
  rc and exact SHA-256 are catalogued in the evidence `report.json`. This
  proves the persistence seam did not exist; it is not a claim about a
  previously failing runtime dock.
* GREEN, final files:
  `PYTHONPATH=. uv run --no-project pytest tests/test_c100_dock_pin_persistence.py tests/test_c100_dock_pinned_items.py tests/test_c100_settings_persistence_isolation.py -q`
  → `51 passed, 2 skipped, 116 subtests passed`, rc=0. The exact log
  SHA-256 for the committed head is catalogued in the evidence `report.json`.
  The adjacent pin-order and settings-isolation files are unchanged negative
  controls.
* CI-style targeted discovery:
  `PYTHONPATH=. uv run --no-project python -m unittest discover -s tests -p 'test_c100_dock_pin_persistence.py'`
  → `Ran 10 tests ... OK (skipped=1)`, rc=0. The log SHA-256 is in
  `report.json`. The single skip is the POSIX mode-bit assertion on Windows,
  where mode bits are not authoritative; it is limited to that one test.
* Mutation proof: disabling the state-version guard in the pre-hardening
  production revision made the corrupt-version subtests fail (rc=1,
  `2 failed, 9 passed, 1 skipped, 31 subtests passed`); the byte-identical
  restore was verified by identical SHA-256 before and after (recorded in
  `report.json`). The unencodable-identifier guard and its two regression
  cases were added afterwards and the final GREEN above re-ran on that final
  code.
* `python tools/check_foundation.py` → `PASS`, rc=0; log SHA-256 is in
  `report.json`.

All artifact SHA-256 values are recomputed from on-disk bytes in
`report.json` with `.sha256` sidecars in the same evidence directory.

## Resource / evidence note

Measured here: test counts, durations and log SHA-256s from local CPython
runs on Windows 11 (`SYNTHETIC`). Deliberately not measured: shell-owned PSS,
CPU, GPU, wakeups, compiled Qt render, real Mint session behavior and
screen-reader behavior — all `NOT_RUN`. Full suite, Qt build and VM are
`NOT_RUN` by directive scope. This is a bounded file-state decision path with
no new service, no continuous work and no accessibility or approved-visual
change, so no stability, security, accessibility or visual tradeoff is made.

## Non-claims

This is a host-side persistence contract. It does not prove that a compiled
Qt dock exposes pin/unpin controls, does not claim a real application
restart, does not establish Linux Mint acceptance and does not alter the
frozen visual identity. The compiled host adapter remains unwired at this
pin; no PR, merge or CI promotion is claimed by this document.
