# Virtual desktop switch request contract (PE-107)

## Purpose

`canopy_features/windows/virtual_desktop_switch_contract.py` is an inert,
host-owned adapter at the existing `canopy_core.host_events` boundary. A
trusted caller emits one of the four documented protocol-v2 host events and may
serialize a *virtual desktop / workspace switch request* against the real
`HostEvent` that was delivered. The result is an immutable, bounded record for
inspection only. It is not an execution path: `WM_REQUESTS = 0`,
`polling = False`, `acceptance = NOT_ESTABLISHED` and
`observation = NOT_PERFORMED` on every record.

There is **no new host-event topic**, field or payload shape. The bus still
accepts exactly `app.catalog.changed`, `window.state.changed`,
`session.state.changed` and `capabilities.report` at protocol version 2. The
module never constructs a `HostEvent` and never echoes a caller value into an
event payload; it only reads the real event envelope (`topic`, `sequence`) and
does not project payload fields.

## Request shape

`VirtualDesktopSwitchRecorder.request(event, *, kind, target, label=None)`
accepts a live `HostEvent` emitted by that same recorder instance plus one of
three fixed request kinds:

- `identifier` — a bounded printable UTF-8 workspace identifier (≤64 bytes);
- `index` — a strict non-negative workspace ordinal, `1..64` (bool and float
  are refused);
- `direction` — exactly one of `next`, `previous`, `first`, `last`.

`label` is optional bounded printable text (≤120 bytes). Unsafe scalars
(controls, format characters, surrogates, private-use and noncharacters),
blank identifiers, unknown kinds and wrong types raise `SwitchRequestError`.
A request is refused unless the event is still inside the recorder's bounded
live-event window; events from another bus, evicted events and closed
recorders cannot authorize a request. Repeating the same `(topic, sequence,
kind, target)` yields an `IGNORED` / `DUPLICATE_REQUEST` record without growing
the store; `ignored_count` counts those refusals.

Records are frozen dataclasses with a fixed scalar field set and a fresh
read-only `MappingProxyType` from `to_dict()`. `snapshot()` returns at most 16
fresh read-only mappings, newest first; `close()` clears all state and makes
later `emit`/`request` calls fail closed.

## Trust and scope boundary

Only trusted host code may call `emit()` or `request()`. Callbacks are the
recorder's own stable bound method, allowlisted at bus construction; no QML,
theme, manifest or external caller can subscribe, choose a topic or invoke a
switch. There is no Qt object, window manager call, compositor observation,
key binding, socket, process, filesystem access, thread, timer, poll, clock,
randomness or network activity. No desktop state is changed and no native or
fallback switch is performed.

This record is deliberately distinct from the PE-086 workspace decision
contract (native-versus-fallback from a workspace inventory and negotiation),
the PR688 window-reference guard, the PE-102 window activation producer and
the PR704 dock running-indicator source. Those modules are neither imported
nor modified here. This contract only serializes a read-only, provenance-bound
serialized switch request; a future reviewed host adapter would own any real
action and must supply its own acceptance evidence.

## Verification

`tests/test_pe107_virtual_desktop_switch_contract.py` uses real bus-emitted
events only (fabricated or foreign events are negative controls). It covers
record shape and immutability, index/identifier/direction targets, bounded
newest-first snapshots, duplicate suppression, live-event authorization,
hostile input, close behavior, the four-topic contract and AST-level guards
against execution/UI/sibling imports. Results are recorded under
`scratch/master_directive_20261126/evidence/virtual_desktop_switch_contracts/`
with SHA-256 sidecars. Targeted, synthetic, in-process only: real Mint
acceptance, WM switching, compiled Qt behavior and screen-reader output are
`NOT_RUN`; no visual asset or protected file is touched.
