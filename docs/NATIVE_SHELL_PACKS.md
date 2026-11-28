# Native Shell Packs (M3): inventory and bounded transactional switching

**Status: CONTRACT + SYNTHETIC HARNESS ONLY.** This document reports an
in-process, pure-Python verification of the eight built-in pack identities and
the transactional switch boundary. It is **not** a compiled Qt, compositor or
Linux Mint desktop result. Final visual acceptance and any release decision
remain owner-gated.

Owner directive: SHA `79e30d79`, cap 8. Base: `ec910d7a` on
`integration/canopy-plasma6-20261127`.

## Owned surface

- `canopy_features/settings/shell_pack_selection.py` — fail-closed inventory,
  future identity validation, and two-phase selection ledger.
- `canopy_features/settings/__init__.py` — re-exports the new contract.
- `tools/shell_packs/roundtrip_harness.py` — deterministic A→B→A harness.
- `docs/NATIVE_SHELL_PACKS.md` — this document.
- `scratch/native_shell_packs/**` — reproducible JSON evidence.

No other path is changed. `prototype/classic/Theme.qml` (dock-geometry agent)
and all approved artwork, wallpaper, icons and geometry are untouched.

## Initial inventory — exactly eight, all included

| # | Reserved identity | Display name | Tier |
|---|---|---|---|
| 1 | `org.canopy.classic` | Classic | included |
| 2 | `org.canopy.modern` | Modern | included |
| 3 | `org.canopy.heritage` | Heritage | included |
| 4 | `org.canopy.flow` | Flow | included |
| 5 | `org.canopy.lite` | Lite | included |
| 6 | `org.canopy.studio` | Studio | included |
| 7 | `org.canopy.cloud` | Cloud | included |
| 8 | `org.canopy.touch` | Touch | included |

`PAID_TIERS` is empty and no identity stores a tier field: there is no premium
edition, paywall or upgrade path. Classic keeps its approved identity; the
inventory is a settings contract, not a visual redesign.

**Unlimited future packs.** `validate_future_pack()` accepts any bounded
non-reserved reverse-DNS identity; there is no numeric cap. Reserved
`org.canopy.*` identities cannot be impersonated by untrusted manifests (the
existing offline checker already rejects that prefix). Acceptance here is
identity validation only — installation, review, signing and execution remain
separate host responsibilities. No plugin marketplace is implied.

**One shared core.** Canopy Core owns the compositor/session, app launcher,
window management, notifications, settings, accessibility and system status.
A pack requests an affordance; it never starts a parallel instance of any of
these services. The harness asserts that at most one presenter is active and
that every prepared presenter is disposed.

## Transactional switch boundary

1. `PackSwitchLedger.prepare(target)` records the pending target and returns a
   one-use token. Reentrant or duplicate prepares are refused; history is a
   bounded deque (`MAX_HISTORY = 16`).
2. The host attempts the presentation transition through the existing
   `canopy_core.shell_host.ShellHost` state machine (validate → prepare →
   deactivate old → activate candidate → dispose old). Only host-registered
   trusted factories are used; pack metadata never becomes executable code.
3. `commit(token)` is the **only** operation that changes the persisted
   selection, and only after a verified success (`SWITCHED`, correct active
   id, no recovery flag).
4. Any failure calls `rollback(token)`: the persisted selection stays on the
   last healthy pack. Failed activation with failed candidate teardown sets
   `RECOVERY_REQUIRED` instead of claiming a seamless switch.

There is no polling, daemon, new host event topic, process, socket or
filesystem write in this contract.

## Reproducible harness

From the worktree root:

```sh
python -m tools.shell_packs.roundtrip_harness --rounds 100 \
  --evidence scratch/native_shell_packs/roundtrip_100.json
```

One round trip is `A → B → A` using adjacent built-ins cycled over all eight
packs. 100 round trips = 200 host switches. The run asserts:

- every switch returns `SWITCHED` with the expected active id;
- the persisted selection changes exactly at the commit boundary;
- at most one presenter is active at any time (peak = 1);
- every created presenter is disposed after the final `stop()`;
- prepare/activate/deactivate failures roll back to the original pack;
- unrecoverable teardown yields `RECOVERY_REQUIRED` with the old selection
  still persisted;
- five invalid targets are rejected before any factory call;
- synchronous reentrancy raises `SwitchBusy` without breaking the outer switch.

Evidence: `scratch/native_shell_packs/roundtrip_100.json` (canonical payload
SHA-256 recorded inside the file) and its byte-identical repeat
`roundtrip_100_repeat.json`. Two consecutive runs produced the same payload
digest. Checksums are in `scratch/native_shell_packs/SHA256SUMS.txt`.
`full_suite.log` is retained and labelled `INCOMPLETE_600S_CAP`: the full
`unittest discover -s tests` run hit the 600-second foreground cap without a
terminal summary, so no full-suite verdict is claimed. The targeted suite
covering settings, pack validation/registry, trusted host lifecycle, focus
adapter, capability report and scaffold ran in this worktree at the same head:
`Ran 254 tests ... OK (skipped=1)` (skip pre-existing).

### Evidence labels (exact)

- `SYNTHETIC` — pure in-process Python with inert presenters.
- `STATIC_PYTHON_HARNESS` — exercises the existing lifecycle state machine,
  not a desktop.
- `NOT_MINT_RUNTIME`, `NO_VISUAL_CHANGE` — no guest session, QML or artwork.
- `NOT_RUN` — native round trip, compiled Qt switcher, pack QML execution,
  screen reader, real-hardware resources and process/socket activity.

### Exact native blocker

`NO_COMPILED_SWITCHER_WIRING`: the base tree contains only the in-process
Python prototype `canopy_core.shell_host.ShellHost` with inert presenters; no
compiled Qt/host entry point calls `ShellHost.switch`. The only non-test
constructor is `canopy_core/capability_cli.py:93` with an empty catalog.
`docs/SHELL_PACK_ARCHITECTURE.md:178-198` explicitly says it is not connected
to Qt, compositor/window state, Mint sessions or live desktop switching. A
Mint VM therefore has no native switcher to exercise. `Canopy-Test-Plasma6`
is registered and running on this host but was **not** used; no guest switch
session was performed (`guest_switch_session = NOT_RUN`). Native acceptance
requires a compiled host adapter plus real window/focus/memory tests and
owner visual approval.

## Resource / evidence note

- Measured: `SYNTHETIC` — bounded allocations only (200 switch records,
  201 inert presenters, selection history capped at 16 entries, no retained
  presenter after `stop()`). No RSS, CPU or PSS measurement was performed.
- `NOT_RUN`: real Mint runtime, compiled Qt, screen-reader announcements,
  HiDPI/layout screenshots, process launch, socket and compositor activity.
- The contract adds no service, timer or long-lived object; it cannot trade
  stability, security, accessibility or approved visuals for a minor gain.
- Screen reader: `NOT_RUN`; no announcement path is touched by this change.
