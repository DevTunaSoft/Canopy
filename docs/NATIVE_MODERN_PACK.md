# Native Shell Packs — initial eight (M3 bounded first-party definitions)

**Status: definitions + metadata-only verification, NOT a running shell.**
This change completes the initial eight first-party Shell Pack identities on
the shared Canopy host: Classic, Modern, Heritage, Flow, Lite, Studio, Cloud
and Touch. It adds no second compositor, service, activation path or telemetry
and does not change approved Classic identity/assets. Owner visual acceptance
and native runtime acceptance remain separate, unresolved gates.

Base: `ec910d7a` (`integration/canopy-plasma6-20261127` tip).
Branch: `product/native-modern-pack-20261128`.

## Initial inventory (bounded at eight, not a ceiling on future packs)

| Pack | Reserved built-in id | Catalog manifest id | Scope (declarative only) |
| --- | --- | --- | --- |
| Classic | `org.canopy.classic` | none (reserved identity) | Approved frozen baseline; no catalog descriptor is authored or rewritten. |
| Modern | `org.canopy.modern` | `io.canopy.modern` | Contemporary panel and spacing within approved identity. |
| Heritage | `org.canopy.heritage` | `io.canopy.heritage` | Traditional layout of the same approved elements. |
| Flow | `org.canopy.flow` | `io.canopy.flow` | Activity/workspace arrangement using existing host APIs. |
| Lite | `org.canopy.lite` | `io.canopy.lite` | Reduced affordances for low-resource hosts. |
| Studio | `org.canopy.studio` | `io.canopy.studio` | Creation/production workspace arrangement. |
| Cloud | `org.canopy.cloud` | `io.canopy.cloud` | Web/remote-work arrangement, account-neutral. |
| Touch | `org.canopy.touch` | `io.canopy.touch` | Touch-friendly geometry within approved identity. |

Unlimited later packs and layout variants remain possible through the existing
independent catalog registry/checker; the eight-entry `MAX_DEFINITIONS` bound
applies only to this checked-in first-party inventory.

## What was added

| Path | Purpose |
| --- | --- |
| `tools/shell_packs/<modern,heritage,flow,lite,studio,cloud,touch>/manifest.json` | Seven valid Shell Pack v1 descriptors: presentation-only, `qt-qml`, `shell_api: 1`, `same-session`, empty `permissions`, no paid/activation/telemetry fields. |
| `tools/shell_packs/<...>/ui/Main.qml` | Seven inert, non-runnable descriptor placeholders. No timer, network, loader or service instance. |
| `tools/shell_packs/<...>/README.md` | Per-pack scope, shared-core boundary and non-goals. |
| `canopy_features/settings/shell_pack_manifest.py` | Shared immutable inventory of all eight identities, one binding table, one host-service ownership view and a bounded 100-round-trip synthetic ledger. |
| `tools/check_shell_pack.py` | Same single-pack checker plus a bounded `--catalog` mode validating all seven descriptors and their id bindings. |
| `tests/test_native_shell_packs_catalog.py` | Eight-identity, free-by-construction, shared-core, checker, all-pairs transition, 100-round-trip and Classic-preservation regressions. |
| `scratch/native_modern_pack/verify_native_modern_pack.py` | Synthetic harness and its JSON/SHA-256 evidence. |

## Identity and Classic preservation

The built-in `org.canopy.*` identities are reserved in the shared module; the
on-disk catalog manifests use non-reserved `io.canopy.*` ids because the v1
checker rejects reserved ids for catalogs. The binding is explicit and grants
no extra authority. Classic is reserved only: no manifest, QML, geometry,
wallpaper, icon or preference is read, rewritten or generated here, and its
approved source marker stays `built-in:approved-classic`.

## One core, one compositor, no duplicate services

Each pack requests only the host affordances in its manifest. The shared host
owns the single compositor/session and one instance of app launching, window
management, notifications, system status, settings and accessibility. Upstream
Plasma 6 / KF6 facilities are reused through that host; no pack starts a
parallel daemon, index, timer or polling loop. `PACK_OWNED_SERVICES` is empty
and a definition with owned services fails closed. Manifest validation is not
a trust decision; community executable QML remains disabled until provenance,
signing and isolation exist.

## Free by construction

Every first-party pack is included at no cost. The shared module exposes
`INCLUDED_TIER = "included"`, `PAID_TIERS = frozenset()`,
`ACTIVATION_REQUIRED = False` and `TELEMETRY_ENDPOINTS = frozenset()`; a
`PackDefinition` cannot be constructed with a paid tier, activation, telemetry
or a pack-owned service. No account, advertisement, unlock or endpoint appears
in any manifest or QML descriptor.

## Lifecycle and the 100-round-trip synthetic harness

`prepare_switch` → `apply_switch` → `verify_switch(healthy)` →
`release_inactive` models bookkeeping only. A failed health verdict restores
the previously committed pack; `rollback_switch` can abort a prepared/applied
candidate, and post-commit rollback is intentionally rejected. No function
loads QML, writes settings, changes a window or contacts the compositor.

`run_synthetic_round_trips` performs exactly 100 deterministic A→B→A round
trips across all eight identities (300 immutable ledger transitions), each
including one failed-verify rollback. The harness records the count,
transition count, sequence digest and `real_runtime_verified: false`. This is
offline bookkeeping, not a live switch or proof that applications survive.

## Verification (SYNTHETIC / NOT_RUN)

```
python tools/check_shell_pack.py --catalog tools/shell_packs
python -m unittest tests.test_check_shell_pack tests.test_shell_pack tests.test_shell_pack_registry tests.test_native_shell_packs_catalog
python scratch/native_modern_pack/verify_native_modern_pack.py
```

The harness writes `synthetic_verification.json` plus a SHA-256 sidecar. Its
report is pinned to the head at generation time; evidence-only commits after
it add no product code. It checks the catalog CLI, eight-definition inventory,
healthy prepare/apply/verify/release, failed-verify rollback, five illegal
transition controls, 100 round trips, owned-path scope with zero Classic path
changes, and absence of paid/activation/telemetry fields or QML runtime hooks.

Explicitly **NOT_RUN**: native Plasma/KWin session switch, live Classic→any
pack switch preserving applications, compiled Qt/QML rendering and screenshots,
owner visual acceptance, real screen-reader/keyboard verification, real
PSS/CPU/GPU measurements, and guest install/rollback/upgrade. No green CI or
metadata check is presented as native product readiness.

## Resource impact

- **SYNTHETIC (measured here):** seven bounded manifests, seven inert QML
  descriptors, one eight-definition inventory and 300 immutable ledger
  transitions; validation only, no background work.
- **NOT_RUN (deliberately):** native idle PSS, CPU over five minutes, GPU,
  wakeups and frame times; no real desktop session was started.
- The change adds no resident process, timer, polling loop or service and
  therefore does not trade stability, security, accessibility or approved
  visuals for a resource gain.
