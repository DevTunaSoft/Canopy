# Native Modern Shell Pack (M3, bounded first-party definition)

**Status: definition + metadata-only verification, NOT a running shell.** This
change adds a bounded first-party Modern Shell Pack definition to the shared
Canopy host. It does not implement a second compositor, a new service, an
activation or purchase path, telemetry, or any change to approved Classic
identity/assets. Owner visual acceptance and native runtime acceptance remain
separate, unresolved gates.

Base: `ec910d7a` (`integration/canopy-plasma6-20261127` tip).
Branch: `product/native-modern-pack-20261128`.

## What was added

| Path | Purpose |
| --- | --- |
| `tools/shell_packs/modern/manifest.json` | Valid Shell Pack v1 descriptor: presentation-only, `qt-qml`, `shell_api: 1`, `same-session` intent, empty `permissions`, no paid/activation/telemetry fields. |
| `tools/shell_packs/modern/ui/Main.qml` | Non-runnable, inert descriptor placeholder. No timer, network, service instance or QML loader. |
| `tools/shell_packs/modern/README.md`, `UPSTREAM_FACILITIES.md` | Identity binding, upstream Plasma/KF6 reuse inventory and explicit non-goals. |
| `canopy_features/settings/shell_pack_manifest.py` | Immutable, data-only first-party inventory and prepare/apply/verify/rollback bookkeeping ledger. |
| `scratch/native_modern_pack/verify_native_modern_pack.py` | Bounded synthetic harness; writes `synthetic_verification.json` and `SHA256SUMS.txt`. |
| `docs/NATIVE_MODERN_PACK.md` | This document. |

## Identity and Classic preservation

The built-in identity is `org.canopy.modern`; the checked-in catalog manifest
uses `io.canopy.modern` because the existing offline checker rejects the
reserved `org.canopy.` namespace for on-disk catalogs. The binding is explicit
in `shell_pack_manifest.py` and grants no extra authority. Classic remains the
reserved built-in `org.canopy.classic` with its approved identity and assets
untouched; the inventory does not read or rewrite Classic presentation files.

## One core, one compositor, no duplicate services

Modern requests host UI affordances only (app launcher, taskbar, workspace
list, window list, system status, settings panel). The host owns the single
compositor/session and one instance of app launching, window management,
notifications, system status, settings and accessibility. Upstream Plasma 6 /
KF6 facilities are reused through that host: application model/desktop
entries, TasksModel/windows, notification source, tray/status, power/network/
audio/display, and accessibility. The pack starts no parallel daemon, index,
timer or polling loop. Manifest validation is not a trust decision; community
executable QML/JS remains disabled until provenance, signing and isolation
exist.

## Free by construction

Every first-party layout is included at no cost. The module exposes
`INCLUDED_TIER = "included"`, `PAID_TIERS = frozenset()`,
`ACTIVATION_REQUIRED = False` and `TELEMETRY_ENDPOINTS = frozenset()`; a
`PackDefinition` cannot be constructed with a paid tier, activation,
telemetry or a pack-owned service. No account, advertisement, unlock or
endpoint appears in the manifest or QML descriptor.

## Lifecycle boundary

`prepare_switch` → `apply_switch` → `verify_switch(healthy)` → `release_inactive`
models only bookkeeping. A failed health verdict restores the previously
committed pack; `rollback_switch` can also abort a prepared/applied candidate.
After commit, rollback is intentionally rejected: recovery must go through a
separate reviewed host flow. No function loads QML, writes settings, changes a
window or contacts the compositor. A `same-session` manifest value is an
intent, not proof of a live switch; unsupported sessions require a clearly
warned logout/login path.

## Verification (SYNTHETIC / NOT_RUN)

`python scratch/native_modern_pack/verify_native_modern_pack.py` ran against
this exact tree and produced `synthetic_verification.json` (SHA-256 sidecar in
`SHA256SUMS.txt`). It checked the offline manifest CLI, first-party inventory,
healthy prepare/apply/verify/release, failed-verify rollback, explicit
rollback, four illegal-transition negative controls, owned-path scope with no
Classic path changes, and absence of paid/activation/telemetry fields or QML
runtime hooks.

Explicitly **NOT_RUN**: native Plasma/KWin session switch, live Classic→Modern
switch preserving applications, compiled Qt/QML rendering and screenshots,
owner visual acceptance, real screen-reader/keyboard verification, real
PSS/CPU/GPU measurements, and guest install/rollback/upgrade tests. No green
CI or metadata check is presented as native product readiness.

## Resource impact

- **SYNTHETIC (measured here):** manifest size 539 B and QML descriptor size
  1033 B; validation is bounded to one manifest, one inventory of two
  definitions and a ledger capped at twelve steps. No background work.
- **NOT_RUN (deliberately):** native idle PSS, CPU over five minutes, GPU,
  wakeups and frame times; no real desktop session was started.
- The change adds no resident process, timer, polling loop or service and
  therefore does not trade stability, security, accessibility or approved
  visuals for a resource gain.
