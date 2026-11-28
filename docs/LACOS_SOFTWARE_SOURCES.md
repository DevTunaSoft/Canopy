# LacOS P0 software sources — bounded policy contract

**Status: PLANNED / POLICY ONLY.** This document specifies and verifies a
**declaration evaluator** and **read-only probe facts** for the five LacOS P0
application ecosystems. It does not install software, verify a real signature,
approve a package, start a runtime, or constitute a Linux/Kinoite guest test.
No real guest was executed for this change: guest acceptance is `NOT_RUN`.

## Authority and scope

- Controlling goal: Rev3 master directive SHA-256
  `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a`
  (sections B6, B7, 12; immutable core and application ecosystems).
- Branch base: `integration/canopy-plasma6-20261127` @ `ec910d7a`.
- Owned paths only: `canopy_features/software_sources/**`,
  `docs/LACOS_SOFTWARE_SOURCES.md`, `scratch/lacos_sources/**`,
  `tools/lacos_sources/**`. No core, test-tree, workflow, visual, hold or
  other-owner file is touched. No merge or self-approval is performed.

## The five P0 ecosystems

| ID | Provenance required | Signature required | Capabilities (maximal) | Isolation / no-core-mutation note |
|---|---|---|---|---|
| `flatpak_flathub` | `official-flathub`, `distribution-flatpak` | `gpg` | search, install, update, remove, launch, permissions | Flatpak sandbox plus explicit portals; no host filesystem, device, socket or privileged service by default; no host core writes. |
| `apt_deb` | `ubuntu-archive`, `debian-archive` | `apt-signed-by` | search, install, update, remove, launch | Only in an Ubuntu/Debian-compatible environment with its own database; no foreign host repo or host library overwrite; no host core writes. |
| `pacman` | `arch-official` | `pacman-key` | search, install, update, remove, launch | Isolated Arch-compatible environment and separate database; **partial upgrades forbidden**; no foreign host repos; no host core writes. |
| `dnf_rpm` | `fedora-official` | `rpm-gpg` | search, install, update, remove, launch | Fedora-compatible environment with signed official sources; no foreign host repo or host library overwrite; no host core writes. |
| `rootless_podman_oci` | `official-registry`, `verified-image` | `cosign`, `sigstore` | search, pull, run, update, remove, permissions | Rootless is **not** a complete sandbox: restrict host files, credentials, devices, sockets, privileged services and network; no privileged defaults; on-demand only, no always-on runtime. |

P1/P2/P3 formats (AppImage, Wine/Bottles, Steam/Proton, PWA, AUR, Snap, Nix,
Zypper, Alpine APK, Waydroid, Homebrew and further ecosystems) are explicitly
out of scope here. No runtime is installed by default; all five P0 paths are
declared `on_demand: true` and `runtime_installed_by_default: false`.

## Explicit rules

1. **No core mutation.** `no_core_mutation` must be `true`. Any manifest that
   requests core writes, boot-artifact changes or host-library replacement is
   rejected; `/usr` and merged binaries/libraries remain immutable in LacOS.
2. **No foreign host repository mixing.** `foreign_host_repo_mixing` must be
   `false`. APT, Pacman and DNF stay in separate compatible environments with
   independent databases; no host repository or host library overwrite.
3. **No partial Arch upgrades.** `partial_upgrade` is in the global forbidden
   capability set and can never be granted, regardless of ecosystem tables.
4. **No privileged default or always-on service.** `privileged`, `always_on`,
   `telemetry`, `paid_tier`, `host_repo_mixing`, `foreign_repo_mix` and
   `core_mutation` are never grantable. All first-party paths are free and open
   source with no paid tier, ads, accounts or mandatory telemetry.
5. **Provenance and signature are requirements, not observations.** A
   manifest may only *declare* upstream provenance, a supported signature
   scheme and `verified: true` in `guest-only` scope. The probe separately
   requires `signature_verified`, `source_verified`, `environment_isolated`,
   `core_mutation_absent`, `foreign_repo_absent`, `no_always_on_service` and
   `privileged_absent`. A declaration alone never grants a capability.
6. **Host presence is not trust.** The read-only host probe uses only a bounded
   tool-presence lookup (`shutil.which`) and never reports a grant. Guest facts
   must be collected inside a disposable guest by an operator; synthetic facts
   exercise the evaluator but always report `guest_acceptance: NOT_RUN`.
7. **Read-only implementation.** The policy modules contain no process launch,
   network call, file write, path resolution, package-manager invocation or
   persistent service. The verifier writes only its evidence JSON under
   `scratch/lacos_sources/evidence/`.

## Bounded manifest contract

`evaluate_manifest(manifest)` accepts one already-parsed mapping:

- top-level fields: `schema_version` (`1`), `target` (`lacos-guest`),
  `no_core_mutation`, `foreign_host_repo_mixing`, `paid_tiers`, `telemetry`,
  `duplicate_always_on_services`, and `ecosystems` (exactly the five P0 IDs);
- each ecosystem: `enabled`, `on_demand`, `runtime_installed_by_default`,
  `capabilities` (1–8), `sources` (1–4);
- each source: `id`, `provenance`, `signature`, `verified`, `scope`;
- bounds: 40 top-level fields, 8 ecosystem fields, 120 characters per string,
  8192 total characters, nesting depth ≤ 6; unknown fields, URI/absolute-path/
  traversal strings, executable-looking keys or values, control characters
  and unsafe Unicode fail closed.

The result is an immutable `ManifestReport`. `VALID` means "internally
consistent declaration only" and carries per-ecosystem isolation notes; it is
not a signature check, an installation approval or guest evidence.

## Probe contract

`collect_host_facts(context)` produces boolean-only, category-level facts and
never runs a package manager. `evaluate_probe(manifest_report, facts)` returns
an immutable `ProbeReport`. `context: host` always yields `HOST_ONLY` with no
grants. `context: guest` yields `READY` and per-ecosystem capability grants
only when every required fact is true and provenance is an allowed upstream
`guest_acceptance: NOT_RUN`, and no caller-declared flag can promote that
field: real guest acceptance belongs to separate in-guest tests, none of
which were run for this change.

## Reproduction

From the worktree root (Python 3.14 on the authoring host):

```sh
python tools/lacos_sources/check_sources.py probe --json
python tools/lacos_sources/check_sources.py manifest --file scratch/lacos_sources/fixtures/manifest_valid.json
python tools/lacos_sources/check_sources.py verify
```

`verify` checks fixture hashes, two static source invariants (no process
execution, no write I/O in the policy modules), five-ecosystem coverage,
forbidden-capability coverage, the valid declaration, host-vs-guest probe
behaviour, no real guest acceptance and 18 negative controls (including a
self-declared live-guest claim that must be rejected). It prints one
`CHECK` line per check and a `SUMMARY` line, and exits nonzero on any failure.
`verify-write` additionally writes
`scratch/lacos_sources/evidence/verification_report.json` with production and
fixture SHA-256 values and per-check statuses.

## Verification evidence (exact head)

- Static/synthetic gate: **29/29 PASS** on the committed head.
- Fixtures: 5 hashed input files plus 18 negative fixture cases; hashes pinned
  in `scratch/lacos_sources/fixtures/SHA256SUMS`.
- Guest probe: **NOT RUN**. Real signature verification, installation,
  isolation enforcement and guest acceptance: **NOT RUN**.
- Evidence labels: `STATIC SOURCE ONLY`, `SYNTHETIC`; no `NATIVE RUNTIME`
  claim is made.

## Resource impact

No new daemon, service, polling loop or background task is added. The policy
modules are pure functions with bounded inputs (at most five ecosystems, four
sources each, 8192 characters); the CLI is short-lived. Runtime RSS/CPU was
**NOT RUN** and is not claimed. No stability, security, accessibility or
approved-visual tradeoff is made; no visual assets are touched.

## Residual blockers

- A real disposable Kinoite/Arch/Fedora/Ubuntu guest must run the read-only
  probe and signature verification before any capability can be treated as
  operational trust.
- Actual Software Center search/install/update/launch/remove wiring, rollback,
  permission UI and package-manager integration are future work.
- Integration to `main` requires independent review and a distinct human
  approving review; this work stays a draft PR with no self-approval or merge.
