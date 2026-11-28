# LacOS P1 multi-ecosystem support — bounded read-only-first capability map

**Status: DRAFT / CONTRACT ONLY. No merge, no approval.** Real guest:
`BLOCKED` / `NOT_RUN`. Base: `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(`integration/canopy-plasma6-20261127`). Controlling goal: Rev3 master
directive SHA-256
`1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a`.
Branch: `product/lacos-multi-ecosystem-20261128`.

This is the final roadmap item for the current LacOS P1 sequence. It adds a
single bounded evaluator that consumes the five P0 ecosystem declarations plus
the atomic-update, backup/recovery and application-isolation contracts, and
projects an **inert capability map** across all five ecosystems. It does not
install, search, launch, update or remove software, does not implement a
runtime or UI, and does not grant a capability.

## Owned paths only

- `canopy_features/multi_ecosystem/**` — pure policy and immutable view types.
- `tools/lacos_multi_ecosystem/**` — deterministic fixture generator, bounded
  verifier CLI and in-directory unit tests.
- `scratch/lacos_multi_ecosystem/**` — synthetic fixtures, hash pins and
  generated evidence only.
- This document.

No core, compiled shell, QML, approved artwork, CI workflow, `tests/` tree or
other owner's path is touched. No upstream unmerged module is imported.

## Read-only consumption of delivered contracts

Upstream artifacts were fetched and hashed read-only; nothing in them was
edited, staged, imported or duplicated into this branch. Exact citations:

| Artifact | Upstream head (read-only) | Representative SHA-256 |
| --- | --- | --- |
| P0 software sources (`product/lacos-software-sources-20261128`) | `616ce171a7b71f69f19060122f53c97ada346662` | `capability_manifest.py` `91ca6a8b…d4d983`, `source_probe.py` `66685a31…981ade` |
| P1 atomic updates (`product/lacos-atomic-updates-20261128`) | `d808c6e852a28063a45fa702a8463a65f3d28ae5` | `contract.py` `65d4b263…82ba6a` |
| P1 backup/recovery (`product/lacos-backup-recovery-20261128`) | `43792968d56945a637e27b790e9cefe3ebf7dabd` | `contract.py` `2907afd1…fb54b1799b` |
| P1 app isolation (`product/lacos-app-isolation-20261128`) | `f4ee9975ce49943c4ee1adf47e9648c21beab5ab` | `policy.py` `2c797e67…bc18d8` |

The full ten-file SHA-256 pin set is in
`canopy_features/multi_ecosystem/contract.py` and is asserted by the verifier.
A synthetic snapshot projects declaration facts from those artifacts; the
evaluator validates the snapshot, not a live system. The five P0 ecosystem
manifests remain `flatpak_flathub`, `apt_deb`, `pacman`, `dnf_rpm` and
`rootless_podman_oci`.

## Capability map

The evaluator accepts one bounded document (≤ 8192 canonical characters, depth
≤ 6, five exact ecosystem IDs, ≤ 8 capabilities and ≤ 4 sources per ecosystem,
≤ 120 printable pathless characters per string). Exact scalar types,
duplicate-key rejection, non-finite constants and huge integers fail closed.

| Capability class | Examples | Map status | Meaning |
| --- | --- | --- | --- |
| Read-only declaration | `search`, `permissions` | `READ_ONLY_DECLARED` | An internally consistent declaration only; no probe result, no grant. |
| Mutating declaration | `install`, `update`, `remove`, `pull`, `run`, `launch` | `DESCRIBE_ONLY` when atomic, backup and isolation gates are all declared; otherwise `BLOCKED_CONTRACT` | Inert description for a future trusted adapter; never executable here. |

Every entry names the contracts it depends on and stable reason codes. The
result is immutable (frozen dataclasses, tuples, mapping proxies) and
deterministic. `grants` is always empty, `launch_permitted` is always `false`,
`guest_acceptance` is always `NOT_RUN`, `runtime` is `BLOCKED_NOT_RUN`, and
`real_guest` is `{status: BLOCKED, gate: NOT_RUN}`. No caller-supplied field can
promote those values: top-level fields are fixed and a real-guest context or
evidence label is refused.

### Hard policy assertions

- **No core mutation.** `no_core_mutation=true` is mandatory; `core_mutation`
  is never a grantable capability; no layered core write, host-library
  overwrite or boot-artifact mutation is described as executable.
- **No foreign host repository mixing.** `foreign_host_repo_mixing=false` is
  mandatory; APT/Pacman/DNF remain in separate compatible environments with
  independent databases; `partial_upgrade` is forbidden.
- **No paid tiers, accounts or telemetry.** All are mandatory `false` at the
  policy layer and forbidden as capabilities.
- **No duplicate services.** `duplicate_always_on_services=false`; the module
  adds no daemon, compositor, polling loop or always-on runtime. Duplicate
  sandbox, compositor and service mechanisms are refused.
- **Read-only first.** Atomic handoff is never executed, restore is never
  promoted past `REVIEW_REQUIRED`, and app isolation only produces upstream
  descriptions. Upstream provenance and signature are declarations, not
  verified observations.

## Reproduction

From the worktree root on the authoring host (Python 3.14.9):

```sh
python -m py_compile canopy_features/multi_ecosystem/*.py tools/lacos_multi_ecosystem/*.py
python tools/lacos_multi_ecosystem/generate_fixtures.py
python tools/lacos_multi_ecosystem/check_multi_ecosystem.py pin --yes
python tools/lacos_multi_ecosystem/check_multi_ecosystem.py verify
PYTHONPATH=. python -m unittest discover -s tools/lacos_multi_ecosystem -p 'test_*.py'
python tools/lacos_multi_ecosystem/check_multi_ecosystem.py map
```

Observed at the committed head: `py_compile` rc=0; bounded verifier
`SUMMARY checks=50 pass=50 fail=0 verdict=PASS`; targeted suite `Ran 29 tests
... OK`; `verify-write` also PASS and writes
`scratch/lacos_multi_ecosystem/evidence/verification_report.json`. The
generator writes 30 synthetic inputs (one snapshot plus 29 negative cases)
and their pins in `scratch/lacos_multi_ecosystem/fixtures/SHA256SUMS`.
The full `unittest discover -s tests` comparison at the exact base tip is
recorded in the PR body; this branch's tests live in the owned tooling
directory, so Foundation CI discovery of them is `NOT_RUN`.

Negative controls cover missing/unknown/duplicate ecosystem, forbidden
capabilities (including core mutation and partial upgrade), paid tiers,
accounts, telemetry, duplicate services, foreign repo mixing, runtime-by-default,
unsigned or wrongly scoped source, wrong provenance, each contract gate,
executed handoff, performed promotion, permitted launch, source pin/head
mismatch, real-guest labels, extra top-level fields, duplicate JSON keys,
huge integers, wrong container types and a real-guest probe context.

## Resource / evidence note

- **SYNTHETIC:** all checks are bounded in-process validations of pure-Python
  values (≤ 8192 canonical characters, five ecosystems, 27 capability entries,
  29 negative fixtures). No RSS, CPU, guest timing or UI frame time was
  measured.
- **NOT_RUN:** real Flatpak/APT/Pacman/DNF/Podman operations, real signature
  and provenance verification, atomic reboot activation, backup restore,
  isolation enforcement, real guest RSS/CPU/GPU, visual acceptance and
  screen-reader announcements (this change adds no UI or announcements).
- **BLOCKED:** real-guest work is outside this contract boundary and no guest
  was provisioned, contacted or mutated.
- No stability, security, accessibility or approved-visual tradeoff is made:
  no compiled input, visual asset, background service or shell-owned runtime
  path is changed.

## Residual blockers

1. A separately reviewed host adapter and disposable real guest must prove
   provenance, signatures, isolation and no-core-mutation before any
   capability can be treated as operational trust.
2. `tests/` mirroring and CI coverage are a follow-up for that path's owner.
3. Integration and any merge require independent review and a distinct human
   approving review. This DRAFT PR was not self-approved and must not be
   merged here.
