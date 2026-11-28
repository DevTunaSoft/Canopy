# LacOS atomic updates — read-only-first transaction contract (P1 foundation)

**Status: FOUNDATION CONTRACT ONLY. NOT AN UPDATER. Real guest: `BLOCKED/NOT_RUN`.**

This document specifies a bounded transaction contract for an immutable,
rpm-ostree/Kinoite-compatible update flow. The code in
[`canopy_features/atomic_updates/`](../canopy_features/atomic_updates/) is pure
in-process policy: it validates synthetic observations and produces immutable
*descriptions* for a future trusted host adapter. It never executes an update,
a rollback, a reboot, a package operation, a process, a D-Bus call, or any
filesystem/network I/O. No core file is read from or written to a real host.

## Authority and boundaries

- Implements the authorized next roadmap item after the P0 sources/Software
  Center delivery, under the 2026-11-27 supplemental directive section 8
  ("Atomic deployment and rollback"). Base: `ec910d7a` of
  `integration/canopy-plasma6-20261127`.
- Owned paths only: `canopy_features/atomic_updates/**`,
  `docs/LACOS_ATOMIC_UPDATES.md`, `scratch/lacos_atomic_updates/**`,
  `tools/lacos_atomic_updates/**`. No shared docs, CI, manifest, `tests/` or
  visual/asset file is changed.
- This is a **design and gate foundation**, not a production foundation
  selection. See the [LacOS vision](LACOS_VISION.md) and
  [Shell Pack architecture](SHELL_PACK_ARCHITECTURE.md). The sibling research
  artifact `docs/LACOS_KINOITE_VALIDATION.md` (open PR #734, not merged at this
  base) carries the upstream source evidence; this document does not duplicate
  or upgrade that evidence.

## Compatibility mapping to rpm-ostree / Kinoite

| Property this contract models | Mapping | Evidence class |
|---|---|---|
| Immutable base image | Deployment observation requires `core_writable=false`; layered core mutation is refused | Engineering mapping to upstream immutable-root design `[INFERENCE]` |
| Content-addressed target commit | 64 lowercase hex `target_digest` compared with the observed `staged_digest` | Engineering mapping to OSTree commits `[INFERENCE]` |
| Signature verification | `signature_state=VERIFIED` plus an explicit `signature_ok` gate | Engineering mapping to signed commits `[INFERENCE]` |
| Retained previous deployment | `Checkpoint` description; `pinned=true` and `checkpoint_retained=true` required | Engineering mapping to rollback deployment `[INFERENCE]` |
| Activation at reboot | `activation_deferred=true`; handoff steps are marked `requires_reboot` | Engineering mapping to boot-time deployment switch `[INFERENCE]` |
| Stock Plasma fallback | `stock_plasma_fallback=true` gate before any handoff | Engineering mapping to stock session fallback `[INFERENCE]` |

Every row is a **contract requirement**, not a verified property of a real
guest. No Fedora/Kinoite command is run or authored here.

## Transaction contract

### Phases (all read-only)

1. `precheck` — validate bounded synthetic inputs; describe a read-only status
   snapshot.
2. `checkpoint` — confirm an already-retained prior deployment. No pin, write
   or mutation is performed by this contract.
3. `prepare` — observe a staged digest; the immutable core is unchanged.
4. `verify` — evaluate every gate below; a failure stops here with zero
   handoff steps.
5. `handoff` — emit inert descriptions for a trusted host adapter; activation
   is deferred to the reboot boundary.
6. `confirm` — describe a read-only post-reboot confirmation. A failed
   confirmation produces a rollback description, never a retry loop.
7. `rollback` — describe a return to the retained checkpoint, also at the
   reboot boundary.

`HandoffStep` carries an abstract interface token (for example
`rpm-ostree-deploy-handoff`), a bounded detail string, `requires_reboot`, and
`executed=False`. Its constructor rejects `executed=True`; a caller cannot
represent an executed step. Output records are frozen dataclasses with tuple
fields.

### Verification gates

All must be satisfied before `READY_FOR_HANDOFF`:

- `signature_ok` and candidate `signature_state == VERIFIED`;
- `digest_match` and `staged_digest == target_digest`;
- `checkpoint_retained`, `pinned` and the observed deployment `retained`;
- checkpoint digest equals the observed booted commit digest;
- `core_immutable` and observed `core_writable == false`;
- `no_layered_mutation`;
- `within_bounds` and candidate size at most 2 GiB;
- `activation_deferred`;
- `stock_plasma_fallback`.

Stable reason codes: `ok`, `candidate-signature-not-verified`,
`staged-target-digest-mismatch`, `rollback-checkpoint-missing`,
`checkpoint-digest-mismatch`, `core-mutation-forbidden`,
`layered-core-mutation-forbidden`, `input-out-of-bounds`,
`activation-not-deferred-to-reboot`, `stock-plasma-fallback-missing`,
`post-reboot-confirmation-failed`, `synthetic-fixture-required`.

Fail-closed input rules: exact scalar types (no bool-as-int, no containers for
text), 64-hex digests, UTC `Z` timestamps, bounded printable text, duplicate
JSON key rejection, unknown/hostile key rejection (command, path, URL,
credential and payload-shaped keys), and translation of CPython's plain
`ValueError` on oversized integers into the domain error.

## Synthetic fixtures and execution evidence

- Schema: `lacos-atomic-updates-fixture/1`; required `label=SYNTHETIC` and
  `guest_status` in `BLOCKED|NOT_RUN`. The `expect` field is a *claim* verified
  against the computed decision, never a self-fulfilling verdict.
- Seven valid fixtures in [`scratch/lacos_atomic_updates/`](../scratch/lacos_atomic_updates/)
  cover ready-handoff, unsigned candidate, mutable core, missing checkpoint,
  out-of-bounds candidate, failed confirmation (rollback handoff) and
  immediate activation. Three hostile fixtures cover duplicate keys, a 5000-digit
  integer and a real-guest claim. Digests are repeated hex characters and
  identify no real commit.
- Gate: [`tools/lacos_atomic_updates/fixture_gate.py`](../tools/lacos_atomic_updates/fixture_gate.py)
  reads fixture JSON, computes SHA-256 for each file, and writes an evidence
  report with `--out`. It never reads a guest or a host deployment.
- Actual local results at branch head: 32/32 targeted unit tests `OK`; 7/7
  synthetic fixtures matched; foundation link check `PASS`. Raw logs and the
  JSON report are under `scratch/lacos_atomic_updates/evidence/`.
- **CI-scope limitation:** these tests live in the owned package, not the
  shared `tests/` tree, so Foundation CI's `unittest discover -s tests` does
  not collect them. The commands above were run locally at the exact head;
  no CI-green claim is made.

## Resource impact and evidence labels

- `SYNTHETIC`: all measurements are in-process, bounded, pure-Python validations
  of synthetic fixtures (32 tests in 0.082 s on the Windows host). No RSS, CPU,
  wakeup, boot or guest timing was measured.
- `NOT_RUN`: real Kinoite guest update, real reboot/activation, stock-Plasma
  session fallback, screen-reader behavior, visual acceptance and compiled
  runtime are all `NOT_RUN`.
- `BLOCKED`: real-guest execution is blocked by the contract boundary and by
  the absence of a disposable Kinoite guest; no credentials or guest mutations
  were attempted.
- Nothing here trades stability, security, accessibility or approved visuals
  for a resource gain: this change adds no background service, timer, poll loop
  or visual asset, and changes no shell-owned runtime path.

## Next milestones (not performed here)

1. Independent trusted host adapter with a real rpm-ostree read-only status
   bridge and explicit capability grants.
2. Real-guest validation on a disposable Kinoite system: signed commit,
   staged digest, rollback checkpoint, reboot activation, stock Plasma
   fallback and post-reboot confirmation.
3. Integration of these tests into a CI-visible suite by an owner of `tests/`,
   without touching this branch's owned paths.

**No merge or approval is requested or performed by this change.**
