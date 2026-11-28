# LacOS backup/recovery contract (P1, planning only)

**Status: CONTRACT DEFINED / SYNTHETIC VERIFICATION ONLY. NOT A RELEASED FEATURE.**
No real Linux Mint/Kinoite guest, atomic deployment, package database, mount or
live owner-data path was contacted. Real-guest backup and restore are
`BLOCKED` / `NOT_RUN`. This document defines a bounded, read-only-first
contract that a reviewed host adapter may later implement; it does not claim
that a working restore has been performed.

## Scope and ownership

This change owns only:

- `canopy_features/backup_recovery/**`
- `docs/LACOS_BACKUP_RECOVERY.md`
- `scratch/lacos_backup_recovery/**`
- `tools/lacos_backup_recovery/**`

Nothing in `canopy_core`, the compiled shell, QML, approved artwork, CI
workflows, `tests/`, or any other feature module is modified. There is no
merge or approval in this change.

## Why immutable Kinoite changes the problem

An immutable atomic desktop (Kinoite / rpm-ostree style) has a read-only
system tree and versioned deployments. A safe backup/recovery design must
therefore obey these invariants:

1. **Read-only first.** Planning, provenance capture and manifest building
   read declared files in bounded chunks. They never write, rename, delete,
   mount, or trigger a deployment. The only durable write in this package is
   a bounded checkpoint JSON inside a caller-supplied *state* directory.
2. **No core mutation.** Only two scopes are describable: `owner_data` and
   `versioned_state`. Immutable system paths, deployment paths, package
   state and `canopy_core` are outside the contract. A logical name whose
   first segment is a denied root (`core`, `deployment`, `usr`, `etc`, `opt`,
   `var`, `boot`, `home`, `root`, `system`, `canopy_core`) is refused with
   `CORE_MUTATION_REFUSED`.
3. **Deployment-aware.** Every plan, provenance record and checkpoint carries
   an opaque bounded deployment label (never a filesystem path). If the
   currently booted deployment differs from the checkpoint's, restore is
   refused with `DEPLOYMENT_CHANGED` instead of applying stale state to a
   different system tree.
4. **Staging, not promotion.** `ALLOW_STAGED` authorizes a reviewed host to
   copy bytes into a dedicated `restore/<name>` staging root only. The last
   contract step is always `REVIEW_REQUIRED before any promotion`; no code
   here promotes a staged file to a live path.

## Contract modules

| Module | Responsibility |
| --- | --- |
| `contract.py` | Bounded value types (`SourceSpec`, `BackupPlan`, `ProvenanceRecord`, `CheckpointRecord`, `RestoreDecision`), canonical JSON, duplicate-key rejection, read-only plan building. |
| `integrity.py` | Bounded SHA-256 file hashing, `IntegrityManifest`, `build_manifest` and fail-closed `verify_manifest`. Read-only. |
| `checkpoint.py` | Durable atomic checkpoint journal with `PLANNING`/`SEALED`/`ROLLBACK`/`FAILED` states and generation counter. |
| `restore.py` | `evaluate_restore`: pure decision function with all safety gates; `valid_restore_root` staging-root validator. No I/O. |

### Bounds

- at most 64 sources; at most 8 MiB hashed per file (streamed in 64 KiB chunks)
- at most 1 MiB canonical document for plans, manifests and checkpoint bytes
- labels ≤ 64 bytes; logical paths ≤ 256 bytes; deployment labels opaque
- at most 32 deduplicated reason codes; checkpoint generation ≤ 1024
- exact-type gating: `bool` is not accepted where `int` is required; bytes,
  containers and `str` subclasses are rejected where a scalar is required

### Fail-closed vocabulary

`parse_bounded_document` rejects duplicate JSON keys, non-finite JSON
constants, plain `ValueError` from huge integers, oversize bytes and invalid
UTF-8. Path helpers reject symlinks at *any* existing component, `..`
traversal, NUL, backslashes, control characters and non-printable scalars.
Every wrong type raises the module's `BackupRecoveryError`; hostile values
return a refused decision rather than a partial PASS.

## Provenance

`ProvenanceRecord` records tool name/version, schema, plan id, deployment
label, a `guest_class` of `SYNTHETIC` or `REAL_GUEST_NOT_RUN`, a bounded
capture label and bounded notes. Its canonical digest is pinned into the
checkpoint. `evaluate_restore` refuses when the provenance digest, plan id or
deployment label no longer matches the checkpoint (`PROVENANCE_MISMATCH`).
Provenance is a claim about *which labels and bytes* a checkpoint describes;
it is not evidence that a real restore succeeded.

## Integrity

`build_manifest` hashes each declared source once and returns a complete
manifest or no manifest at all — a partial build is never returned. Reading
is bounded and never follows symlinks. `verify_manifest` re-hashes every
entry immediately before a restore decision and compares size **and**
digest. Missing, oversize, unreadable, unsafe-path and changed bytes produce
`MISSING`/`OVERSIZE`/`UNREADABLE`/`UNSAFE_PATH`/`MISMATCH`, all of which
downgrade the decision to `REFUSE`. A manifest digest is additionally pinned
into the sealed checkpoint, so a checkpoint sealed over different bytes is
refused.

## Rollback interaction

An atomic update rollback takes precedence over a backup restore:

- `CheckpointJournal.mark_rollback` records the target deployment and bumps
  the generation. `recover()` then returns `WAIT_ROLLBACK` even for an
  otherwise sealed checkpoint.
- `evaluate_restore` refuses with `ROLLBACK_IN_FLIGHT` while that marker is
  present. A host must call `finish_rollback` (settling on the deployment
  actually booted) before a restore can be considered.
- Because the settled deployment label changes, a restore planned against
  the pre-rollback deployment is refused with `DEPLOYMENT_CHANGED` unless a
  reviewed host re-plans. This prevents stale config from being staged onto
  a different atomic deployment.

### Compatibility with the in-flight P1 atomic-updates contract

The sibling `product/lacos-atomic-updates-20261128` branch defines a retained
previous deployment (`Checkpoint`: `deployment_id`, `commit_digest`, `pinned`,
`created_at`) and prohibits core mutation and immediate activation. This
package does **not** import that unmerged module. Instead,
`RollbackCheckpointView` mirrors those four fields as bounded plain values,
and `evaluate_restore(..., rollback_view=...)` refuses with
`ROLLBACK_CHECKPOINT_MISSING` / `ROLLBACK_NOT_PINNED` when no pinned rollback
checkpoint exists. Both contracts stay read-only-first, emit inert
descriptions rather than executed steps, and label real guests
`BLOCKED`/`NOT_RUN`. No dependency on the atomic-updates branch is created.

## Owner-data safety

- Restore destinations must satisfy `valid_restore_root`: a bounded path
  under `restore/` with no system/core/home/deployment segment.
- A logical name that already exists in the staging root blocks restore with
  `OWNER_DATA_CONFLICT` unless the caller supplies a bounded, explicit
  acknowledgement for that exact name. Silence never means consent.
- Contract steps name only `STAGE <logical> -> <staging-root>/<path>` and a
  final `REVIEW_REQUIRED`. No live owner file is overwritten or deleted by
  this package.

## Verification evidence

Evidence lives in `scratch/lacos_backup_recovery` and is regenerated by
`tools/lacos_backup_recovery/run_contract_checks.py`:

- `evidence_synthetic.json` — 22/22 checks passing on deterministic
  synthetic fixtures; each artifact carries a SHA-256.
- `evidence_synthetic.json.sha256` — LF-only sidecar for the evidence file.
- `fixture/` — generated source/state trees with fixed bytes; tamper and
  restore-detection gates are exercised then the fixture is restored to its
  deterministic bytes.

`tools/lacos_backup_recovery/test_backup_recovery_contract.py` holds 13
unittest cases covering planning bounds, manifest tamper detection,
checkpoint/rollback transitions, every restore gate and wrong-type fail-closed
behavior. Run with:

```
PYTHONPATH=<worktree-root> python -m unittest discover -s tools/lacos_backup_recovery -p 'test_*.py'
```

The tests are intentionally inside the owned tooling directory because
`tests/` is outside this change's ownership. Mirroring them under `tests/`
for Foundation CI is a follow-up for an agent that owns that path; until
then CI coverage of this module is `NOT_RUN` (host-local runs only).

## Resource / evidence note

- **Measured (`SYNTHETIC`):** host-local wall time for the 13 unittest cases
  (≈3.2 s on this Windows host) and 22 synthetic checks; bounded allocations
  only (≤8 MiB streamed per file, ≤1 MiB documents). No real runtime RSS or
  CPU profile was taken.
- **Not measured (`NOT_RUN`):** real Kinoite/Mint guest install, rpm-ostree
  transaction behavior, live owner-data throughput, real device I/O, and
  screen-reader announcements (this change has no UI and emits no
  announcements).
- The contract deliberately trades no stability, security, accessibility or
  approved visual behavior for a minor gain: it is pure Python with no
  background service, no polling and no compiled/visual input.

## Limitations

This is a contract and synthetic harness, not an implemented backup tool.
There is no guest probe, no real deployment inspection, no encryption, no
deduplication, no cross-process locking (single owner only), no threads and
no Qt/host wiring. Any claim that backup or restore works on a real system
requires a separately reviewed host adapter and real-guest acceptance, both
of which are out of scope here.
