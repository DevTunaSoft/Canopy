# LacOS unified Software Center — bounded presentation wiring

Status: **declaration-only presentation**, DRAFT — no merge, no approval, no
promotion. Base `ec910d7a7275296ecbc8b5e5c459d356205165d1`. Controlling goal:
Rev3 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a`.

This change wires a single, read-only Software Center presentation over the
bounded P0 source capability manifest of PR #753. It does **not** install,
search, launch, update or remove software on a host or guest. It does not
implement a search/install/update/launch/remove/permissions runtime and it does
not open a UI. No real guest, package manager, repository, service, core image
or Software Center runtime was executed: all runtime work is
`BLOCKED` / `NOT_RUN`.

## Read-only source consumption

PR #753 (`https://github.com/DevTunaSoft/Canopy/pull/753`) is OPEN and unmerged.
Its source files were fetched into a separate detached worktree and evaluated
there; nothing in that PR was edited, staged, committed or duplicated into this
branch's production code.

| Item | Value |
| --- | --- |
| Consumed PR | #753, head `616ce171a7b71f69f19060122f53c97ada346662` |
| Consumed base | `ec910d7a7275296ecbc8b5e5c459d356205165d1` |
| Consumption | `read-only` (detached worktree, clean before and after) |
| `capability_manifest.py` SHA-256 | `91ca6a8bd677c7a584b6c89ada7bb737b5c3a8bbe9da7b1c4cba21344df4d983` |
| `source_probe.py` SHA-256 | `66685a317e745cddaf33f7c6d92b7d4fe195bc83716b43c55683ac292d981ade` |
| PR #753 bounded verifier | `SUMMARY checks=29 pass=29 fail=0 verdict=PASS` |
| Projected snapshot SHA-256 | `78b1a192deed354ae0ef92496d2d1d3c0c8278db7457f5e41ac71a64996320a4` |

The projection fixture is generated from PR #753's *real* evaluator output over
its synthetic fixtures (`manifest_valid.json`, `probe_guest_synthetic.json`,
host read-only probe). It is pinned by SHA-256 and validated by this branch's
verifier before presentation. `accounts` is an explicit Software Center policy
overlay: PR #753 has no account field, so the snapshot denies accounts and the
adapter requires `accounts=false`.

## Five P0 ecosystems presented

All five cards are `DECLARED` only. Signature status is
`DECLARED_NOT_VERIFIED`: a signature *scheme* is declared by the source, but no
signature was checked on a real guest. `core_mutation=ABSENT_DECLARED` means the
declaration forbids core mutation; it is not proof from a running system. Every
`probe_status` and `guest_acceptance` is `NOT_RUN`.

| Ecosystem | Provenance (declared) | Signature scheme | Signature status | Isolation notes | Core mutation |
| --- | --- | --- | --- | --- | --- |
| Flatpak / Flathub | `official-flathub` (also allows `distribution-flatpak`) | `gpg` | `DECLARED_NOT_VERIFIED` | Flatpak sandbox with explicit portal permissions; no host filesystem, device, socket or privileged-service access by default | `ABSENT_DECLARED` |
| APT / DEB (Ubuntu and Debian) | `ubuntu-archive` (also allows `debian-archive`) | `apt-signed-by` | `DECLARED_NOT_VERIFIED` | Own compatible environment and own database; no foreign host repository or host library overwrite | `ABSENT_DECLARED` |
| Pacman (Arch) | `arch-official` | `pacman-key` | `DECLARED_NOT_VERIFIED` | Isolated Arch-compatible environment with separate database; no partial upgrades and no foreign host repos | `ABSENT_DECLARED` |
| DNF / RPM (Fedora) | `fedora-official` | `rpm-gpg` | `DECLARED_NOT_VERIFIED` | Fedora-compatible environment; signed official sources, no foreign host repository or host library overwrite | `ABSENT_DECLARED` |
| Rootless Podman / OCI | `official-registry` (also allows `verified-image`) | `cosign` | `DECLARED_NOT_VERIFIED` | Rootless Podman is not a complete sandbox: restrict host files, credentials, devices, sockets, privileged services and network; no privileged defaults and no always-on runtime | `ABSENT_DECLARED` |

The projection only carries capabilities declared by PR #753: search, install,
update, remove and launch for the package ecosystems; Flatpak and Podman also
declare permissions; Podman declares pull/run. Forbidden capabilities —
`core_mutation`, `host_repo_mixing`, `partial_upgrade`, `privileged`,
`telemetry`, `paid_tier`, `always_on`, `accounts` — are rejected before any
card is produced.

## Explicit policy assertions

- **No core mutation.** `no_core_mutation=true` is required; every card reports
  `ABSENT_DECLARED`. Normal application install must not modify the booted core.
- **No paid tiers or accounts.** `paid_tiers=false` and `accounts=false` are
  required; no paid, unlock, subscription, activation or account capability is
  presentable.
- **No telemetry.** `telemetry=false` is required.
- **No duplicate services.** `duplicate_always_on_services=false` is required;
  this wiring adds no daemon, compositor, polling loop or always-on service.
- **No foreign host repository mixing.** `foreign_host_repo_mixing=false` is
  required.
- **On demand only.** Every card is `runtime_installed_by_default=false` in the
  consumed declaration; no runtime is installed by default.
- Rootless containers are not presented as complete security sandboxes.

## Files owned

- `canopy_features/software_center/__init__.py`, `center.py` — pure, immutable,
  read-only adapter. No file I/O, process, network, socket, service or import of
  the unmerged PR.
- `tools/lacos_software_center/check_center.py` — `view`, `verify`,
  `verify-write`, `pin --yes` CLI. This is an explicit bounded gate; no file
  was added under `tests/` because that path is outside this task's ownership,
  so Foundation's `unittest discover -s tests` does not discover this verifier.
- `scratch/lacos_software_center/fixtures/**` — one projected snapshot, 14
  synthetic negative fixtures, `negative_cases.json` and `SHA256SUMS`.
- `scratch/lacos_software_center/evidence/**` — generated consumption record
  and verification report.
- This document.

No other path is touched. No visual, QML, C++, artwork, workflow, core, test or
protected path is modified.

## Reproduction

Run from the worktree root:

```sh
python -m py_compile canopy_features/software_center/*.py tools/lacos_software_center/*.py
PYTHONPATH=. python tools/lacos_software_center/check_center.py verify
PYTHONPATH=. python tools/lacos_software_center/check_center.py view
PYTHONPATH=. python tools/lacos_software_center/check_center.py verify-write
sha256sum -c scratch/lacos_software_center/fixtures/SHA256SUMS   # run from fixtures dir
```

Observed at head `ec910d7a` + this change:
`python -m py_compile` rc=0; bounded verifier
`SUMMARY checks=38 pass=38 fail=0 verdict=PASS` (report SHA-256
`62b41567e5c74cc778508ec07b01193d7dd1903890fa7c68c4166ee5e9ab3492`);
consumption record SHA-256
`2c44b42c3026cb77c1412ffbd59efee654d596f9d3d548f4e81b9d7ee6d4e26a`.
PR #753's own verifier was re-run read-only in its detached worktree and passed
29/29 at its exact head.

Negative controls fail closed with pinned reason codes: unknown/missing
ecosystem, paid tiers, accounts, telemetry, core mutation, duplicate services,
foreign repo mixing, a `VERIFIED` signature claim, a privileged capability, a
`READY` probe claim, a native-runtime claim, a wrong field type and a duplicate
JSON key. In-process hardening checks additionally reject unordered containers,
a string used as a sequence, a non-mapping top level, an extra top-level field,
a changed source SHA-256 pin, a native-runtime evidence label and a caller
claiming guest acceptance.

## Resource impact

Measured: **SYNTHETIC** — two bounded pure modules (at most five cards, eight
strings per field, 8192 characters of snapshot input) plus a short-lived CLI;
AST checks prove no process/network call and no write I/O in production code.
Deliberately not measured: real guest RSS/CPU, package-manager I/O, UI frame
times and Software Center runtime — **NOT_RUN**. Screen-reader announcements:
**NOT_RUN** (this change exposes text lines only and adds no UI or accessibility
surface). No stability, security, accessibility or approved-visual tradeoff is
made; no visual path is touched.

## Residual blockers

1. Real disposable-guest signature verification, provenance checking, isolation
   enforcement and no-core-mutation evidence remain `NOT_RUN`; they are required
   before any operational capability grant.
2. Actual Software Center search/install/update/launch/remove/permissions UI and
   rollback remain future work. This PR is wiring/presentation only.
3. PR #753 is unmerged; this branch does not import it at runtime and does not
   depend on its paths existing at the integration tip.
4. Integration/main remain owner-gated; a distinct human approving review is
   required. This DRAFT PR was not self-approved and must not be merged here.
