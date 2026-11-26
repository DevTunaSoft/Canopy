# Classic dock running-indicator source contract (PE-094)

The Classic dock shows a running indicator when an approved app owns at least
one live process. `canopy_features/dock/dock_running_indicators.py` already
owns the bounded, immutable **state model** for that decision. This document
specifies the missing **source contract**:
`canopy_features/dock/dock_running_indicator_source.py`, which projects trusted
window-state events into the indicator events that state model accepts. Its
targeted checks live in `tests/test_c100_dock_running_indicator_source.py`.

This is a source-level contract only. It adds no event topic, no Qt/QML, no
window-manager or compositor access, no icon, wallpaper, dock geometry, colour,
typography or other approved-visual change, and no change to a protected file.

## Trust boundary

A trusted host adapter owns the real window-state source. It observes windows
and classifies each reference using the already-merged window-state capability
contract (`canopy_features/windows/window_state_capabilities.py`, PR688). That
adapter supplies immutable `WindowStateEvent` records to `project()`. This
module:

- imports the four status tokens (`LIVE`, `STALE`, `UNKNOWN`, `UNAUTHORIZED`)
  from PR688 but does **not** register, resolve or authorize a window
  reference, touch its registry, or reimplement its validation;
- consumes only the owner app id carried by a trusted event, and never reads,
  imports or emits a workspace record (`workspace_state_contract.py`,
  `workspace_inventory.py`, `workspace_reconciliation_snapshot.py`), which are
  the PE-086 scope;
- does not observe a window, launch a process, poll, tick a timer, use a
  thread, clock, socket, environment variable or file, and creates no Qt
  object. No compiled consumer is wired here and no Mint acceptance is claimed.

## Event shape

`WindowStateEvent` is frozen, with exactly six fields:

| field | type | contract |
| --- | --- | --- |
| `sequence` | `int` | source monotonic sequence, `0..2_147_483_647`, not `bool` |
| `status` | `str` | one of the four imported PR688 status tokens |
| `app_id` | `str` | owner id, `[A-Za-z0-9._-]{1,128}`, not empty |
| `pid` | `int` | owner process, `1..2_147_483_647`, not `bool` |
| `window_id` | `int` | trusted window instance, `1..2_147_483_647`, not `bool` |
| `opened` | `bool` | `True` when the window appeared, `False` when it vanished |

Every field is validated before any projection. Wrong types (including `bool`
where an `int` is required), unhashable statuses, oversized or hostile app ids,
out-of-range ids and unbounded batches raise `SourceContractError` with no
partial result. Only `list`/`tuple` input is accepted: `str`, `bytes`, mappings,
sets and lazy iterables cannot define a bounded ordered batch.

## Projection rule

`project(state, events)` returns an immutable `Projection` with the final
`sequence`, the projected `AppStarted`/`AppExited` events in arrival order, an
`ignored` count and the resulting indicator `state`.

1. Iterate events in arrival order. An event whose `sequence` is not strictly
   greater than the current projection sequence is stale and ignored.
2. Every event with a newer sequence advances the projection sequence, even
   when it is ignored, so an old event cannot be replayed later.
3. Only `REF_LIVE` events are projected: `opened=True` becomes `AppStarted`,
   `opened=False` becomes `AppExited`. `STALE`, `UNKNOWN` and `UNAUTHORIZED`
   events are dropped and counted as ignored. The source's classification is
   consumed, never second-guessed.
4. The projected events are folded once through
   `dock_running_indicators.apply_events`. The existing per-app PID cap (8),
   app cap (64), PID-reuse transfer and duplicate-owner-PID rejection remain in
   force, so the source cannot inflate an indicator claim.
5. `apply_window_events()` is the convenience entry point returning only the
   resulting indicator state.

Bounds are fixed: at most 1024 events per batch, at most 1024 projected
events, and one new indicator allocation per batch. The module is event-driven
and performs no polling or background work.

## Stale-reference negative controls

`tests/test_c100_dock_running_indicator_source.py` proves that:

- a `STALE`, `UNKNOWN` or `UNAUTHORIZED` event produces no indicator and is
  counted as ignored, while a later `LIVE` event still applies;
- an out-of-order (lower-sequence) event cannot resurrect or clear an
  indicator, and a duplicate sequence is idempotent;
- a close for an app with no live owner cannot manufacture an indicator;
- malformed, oversized and wrong-type input fails closed, with the caller's
  state left unchanged;
- the module imports no OS/Qt/thread/socket/time module (AST-level guard).

These are offline, deterministic checks. They do not compile Qt, run a desktop
session, observe a compositor or claim Linux Mint acceptance.

## Resource / evidence note

- `SYNTHETIC`: the only measured work is bounded, in-process event folding in
  the targeted unittest run (≤1024 events, one indicator allocation per batch).
  No wall-clock or RSS target is asserted for this pure composition layer.
- `NOT_RUN`: real desktop/runtime PSS and CPU, compiled Qt self-tests, real WM
  notification delivery and Linux Mint acceptance were not run.
- `screen-reader`: not applicable — the module emits no announcement and
  changes no accessibility metadata.
- Exact head SHA, targeted-test output and SHA-256 digests for this evidence
  are recorded under `scratch/master_directive_20261126/evidence/dock_running_indicators/`.
