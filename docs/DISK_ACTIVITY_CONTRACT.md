# Disk-activity reduction contract (PE-070)

Status: **pure contract implemented and targeted-tested**. Base integration tip
`ea2b92fa034c598a16fb856169d0a00cb5e0e09f`. This change owns only
`canopy_features/reliability/disk_activity_contract.py`,
`tests/test_c100_disk_activity_contract.py` and this document. It does not edit
an existing writer, compiled UI, approved artwork, protected PR path or
workflow, and it performs no disk write of its own.

## Why this exists

Catalog and cache writers currently save on their own host schedules. The
contract separates *deciding that a snapshot is dirty* from *performing a
write*, so a host can coalesce bursts of changes and flush once on an explicit
lifecycle event (shutdown, settings commit, catalog refresh). No background
poll loop, timer or thread is introduced.

## API

- `WriteTarget(name, max_payload_bytes)` declares a host-owned write stream.
  Names are 1-48 lowercase ASCII letters, digits or `_`, beginning with a
  letter; no path syntax, separators, controls or host paths. Each payload
  bound is a strict `int` in `1..65536`.
- `DiskWriteCoalescer(targets=DEFAULT_TARGETS)` holds at most 32 targets.
- `mark_dirty(name, payload)` accepts exact `bytes` only. Repeated marks for
  the same target replace the one pending payload (last value wins) and
  increment a bounded coalescing count; they do not queue extra writes.
- `flush()` emits all pending writes in first-dirty target order;
  `flush(names)` emits only those explicitly named pending targets in caller
  order. Both return an immutable tuple of `WriteIntent(target, generation,
  payload)` records and clear exactly what they emit. An empty flush emits an
  empty tuple and performs no wait.
- `invalidate(name)` drops one pending write; `invalidate_all()` drops all
  pending writes. Neither emits an intent.
- `snapshot()` returns immutable, payload-free counts, pending target names and
  the fixed negative claims. `to_dict()` is a read-only mapping of the same
  information; payload bytes never appear in diagnostics.

## Bounds and fail-closed rules

| Guard | Ceiling | Refusal |
| --- | --- | --- |
| Declared targets | 32 | `DiskActivityError` on the 33rd target |
| Target name | 48 printable lowercase ASCII chars | `DiskActivityError` on other text or types |
| One payload | `min(caller bound, 65536)` bytes | `DiskActivityError` on empty, oversized or wrong-type payloads |
| Total pending payload | 262144 bytes | `DiskActivityError`; existing pending state is unchanged |
| Generations and counters | 4096 | saturate, never grow without bound |

Unknown, duplicate, unhashable or wrong-type names fail closed before any
state changes. A rejected payload leaves the previous pending payload intact,
so a hostile caller cannot manufacture an extra write or lose a valid one.

## Explicit negative claims

`FIXED_CLAIMS` is emitted in every snapshot:
`coalesced_last_value_wins`, `explicit_invalidation`, `no_filesystem_io`,
`no_payload_in_diagnostics`, `no_polling`, `no_threads`, `no_timers`.
A static source gate checks that the module imports no clock, thread, timer,
scheduler, socket, subprocess or filesystem module and contains no sleep or
`while True` loop. The module emits intents; executing I/O is the host's job.

## Verification and evidence honesty

Targeted synthetic tests: `python -m unittest
tests.test_c100_disk_activity_contract -v` — 12 tests, no real files, no
clock, no threads. RED runs were captured for the missing module, the missing
explicit-control API and the missing bounds/claims; each GREEN run followed a
minimal implementation step. A scratch-only mutation of the coalescing counter
guard changed two named tests from PASS to FAIL while the production file's
SHA-256 stayed byte-identical.

- `SYNTHETIC`: all unittest and mutation results above, on Python 3.14.10 on
  this Windows host.
- `NOT_RUN`: real disk write counting or disk stress, five-minute shell-owned
  PSS/CPU, scheduler wakeups, Linux Mint guest acceptance, compiled Qt runtime
  and visual/accessibility review. No runtime write reduction is claimed; the
  contract only bounds and coalesces pending write requests.
- `screen-reader`: not applicable to this payload-free, non-visual module and
  not run as a runtime test.

Evidence artifacts and SHA-256 sidecars are in
`scratch/master_directive_20261126/evidence/disk_activity_contracts` under the
repository root. No merge to `main` and no promotion out of draft is performed
by this change.
