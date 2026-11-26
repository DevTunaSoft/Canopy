# Classic trusted window-activation snapshot producer

Scope: **host-side, pure-Python source contract only**. The owned files are
`canopy_features/apps/window_activation_producer.py`,
`tests/test_c100_window_activation_producer.py` and this document. No QML,
icon, wallpaper, dock geometry, typography, colour, theme, launcher,
`main.cpp`, `CMakeLists.txt`, workflow or existing Workspace test is changed.

This change does **not** compile Qt, connect to a window manager, inject a
record into the running Classic host, or claim Linux Mint / owner visual
acceptance. Host injection is a later serialized step that requires ownership
of `prototype/classic/main.cpp` and is explicitly deferred here.

## Why this exists

The existing activation path is synthetic: the compiled host builds its
trusted snapshot locally from the Qt platform name and the GIO launcher
allowlist (`hostActivationSnapshot` in `prototype/classic/main.cpp`). The
focus-decision and workspace-inventory models already exist as tested pure
Python contracts but were never composed into the exact host snapshot shape.
This module supplies that composition as a read-only producer so a later host
step can serialize and apply a record built from trusted, already-tested
inputs instead of inventing state in the C++ layer.

## Composition and exact schema

`compose(workspace, focus_broker, switcher_state, *, backend, sequence,
launcher_enabled, installed, policy=None)` first delegates the three state
models to `canopy_features.windows.focus_decision_snapshot.compose`, the
already-tested composition of:

* `windows/workspace_inventory.py` -- canonical workspace identifiers and
  skipped-record notes;
* `windows/focus_intents.py` -- the deny-by-default focus broker and optional
  `PermissionPolicy`;
* `windows/switcher_state.py` -- the frozen keyboard-selection view.

It then adds host-owned facts and emits exactly the eight keys the compiled
`WindowActivationState::applySnapshot` requires, in fixed order:

| Key | Type / value | Provenance |
| --- | --- | --- |
| `schema` | `int` `1` | producer constant; matches `kSchema` |
| `sequence` | `int`, `0..2_147_483_647` | trusted host fact, strict int (`bool` refused) |
| `backend` | `str` in `KNOWN_BACKENDS` (`x11`, `wayland`, `headless`) | host fact, pinned to the window-state capability contract |
| `negotiation` | `SUPPORTED` for `x11`/`wayland`, `PARTIAL` for `headless` | derived from backend, mirroring the host source |
| `launcherEnabled` | `bool` | trusted host fact |
| `installed` | `tuple` of approved dock names, canonical order | launcher install set intersected with the fixed approved-name list |
| `owners` | `()` | always empty: no process telemetry is invented |
| `grants` | `()` | always empty: no permission telemetry is invented |

The optional compiled `focus` sub-object is deliberately never emitted, so no
focus-actuation claim can be manufactured from a pure decision history. The
approved-name order mirrors the host (`Browser`, `Mail`, `Files`, `Calendar`,
`Photos`, `Music`, `Terminal`, `Settings`); `installed` is deduplicated and
projected in that order, so equal inputs always give equal output bytes.

`to_dict()` returns a fresh `MappingProxyType` with fixed key order and
immutable tuple values. `to_json_bytes()` is a serializer for a future host
step: it emits deterministic JSON whose tuples become the arrays the compiled
consumer reads as `QVariantList`. Serializing is **not** injecting.

## Fail-closed behaviour

Every guard raises the module's `ProducerError` before any record is built;
no built-in `TypeError`/`ValueError` leaks from a hostile container, and there
is no partial result.

* Wrong-type, unknown, empty, oversized or unhashable `backend`.
* `sequence` that is a `bool`, negative, oversized, text or a container.
* `launcherEnabled` that is not a strict `bool`.
* `installed` given as `str`, `bytes`, `bytearray`, `set`, `frozenset`,
  `Mapping`, generator or any non-`list`/`tuple` container; more than 64
  entries; duplicates; a non-`str` name; a lowercase/alias name; an
  over-long name.
* Malformed workspace/focus/switcher/policy objects, or any record rejected
  by the underlying composition contract.
* A focus-decision record whose status is `BLOCKED` -- a denied, stale,
  unknown-target or failed-activation decision is never republished as a
  trusted activation snapshot. This is a cross-field guard, not a status
  passthrough.

## Evidence and honest labels

* `SYNTHETIC`: the 18 targeted Python tests exercise composition, exact key
  set/types, canonical ordering, deterministic JSON bytes, fail-closed
  hostile inputs and purity (an AST import scan and a mocked `open()`). No
  wall-clock timing or real-hardware measurement is claimed.
* `NOT_RUN`: compiled Qt build and `--self-test-window-activation-fixture`,
  real window-manager/backend negotiation, X11/Wayland focus actuation,
  Linux Mint guest acceptance, screen-reader announcement and owner visual
  approval. None of these are implied by this pure module.
* `NOT_RUN`: host injection of the produced record into `main.cpp`; that file
  is owned by another workstream and is untouched here.

No resource claim is made beyond bounded, immutable Python data (at most 64
installed names and a 32-bit sequence). No PSS, CPU or timing number is
reported; none was measured.

Related contract: [Classic launcher runtime catalog](CLASSIC_LAUNCHER_RUNTIME_CATALOG.md).
