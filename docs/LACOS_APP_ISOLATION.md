# LacOS P1 application-isolation foundation (contract only)

**Status: CONTRACT DEFINED / SYNTHETIC VERIFICATION ONLY. NOT A RELEASED
FEATURE.** No real Linux Mint/Kinoite guest, Flatpak installation, bubblewrap
namespace, xdg portal, systemd unit, compositor or application launch was
contacted. Real-guest isolation is `BLOCKED` / `NOT_RUN`. The only successful
outcome in this package is an inert description with a `REVIEW_REQUIRED` final
step; no code here launches an app or grants a capability.

## Authority and ownership

- Controlling goal: Rev3 master directive SHA-256
  `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a`
  (sections B4, B6, B7, B11, B12; upstream reuse, immutable core, application
  ecosystems, provenance, no paid tiers/telemetry/accounts).
- Branch base: `integration/canopy-plasma6-20261127` @ `ec910d7a`.
- Owned paths only: `canopy_features/app_isolation/**`,
  `docs/LACOS_APP_ISOLATION.md`, `scratch/lacos_app_isolation/**`,
  `tools/lacos_app_isolation/**`. No core, compiled shell, QML, approved art,
  CI workflow, `tests/`, or other feature module is changed. No merge or
  approval is performed by this work.

## What "reuse upstream" means here

LacOS must not ship a second sandbox, compositor, session daemon or service.
The contract therefore names only surfaces owned by existing upstream
components:

| Mechanism id | Upstream owner | Boundary used by this contract |
| --- | --- | --- |
| `flatpak_sandbox` | Flatpak using the distribution's bubblewrap | per-app namespace; no host core writes |
| `flatpak_portal` | xdg-desktop-portal document portal | read-first file access, no raw guest path in a request |
| `xdg_dbus_proxy` | Flatpak xdg-dbus-proxy | filtered session bus, no raw host socket |
| `systemd_user_scope` | systemd user manager transient scope | per-app cgroup in the existing manager, no new daemon |
| `systemd_unit_sandboxing` | systemd unit sandboxing directives | strict system protection, read-only home view, private tmp |
| `rootless_oci` | rootless Podman/OCI runtime | on-demand only; rootless is **not** a complete sandbox |

Public upstream references (read-only documentation, no code vendored):
[Flatpak sandbox documentation](https://docs.flatpak.org/en/latest/sandbox-permissions.html),
[Flatpak portal documentation](https://docs.flatpak.org/en/latest/portal-api-reference.html),
[bubblewrap](https://github.com/containers/bubblewrap),
[systemd.exec sandboxing](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html),
[systemd.resource-control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html).
No mechanism is bound, configured or started by this package. The catalog is
fixed at six surfaces; a caller requesting a private `own_sandbox` or a
compositor/service mechanism is refused (`MECHANISM_NOT_UPSTREAM`,
`DUPLICATE_SANDBOX_REFUSED`).

## Contract modules

| Module | Responsibility |
| --- | --- |
| `contract.py` | Canonical JSON, bounded value types, exact-type gates, `IsolationRequest` / `IsolationDecision`, digests. |
| `upstream.py` | Fixed upstream mechanism catalog, ecosystem-to-mechanism and permission maps, inert description builder. |
| `policy.py` | Pure `evaluate_request`: provenance/signature gating, least privilege, no core mutation, no duplicate stack, real-guest block. |

### Read-only-first request

A request is a bounded document (≤ 1 MiB canonical bytes) with:

- one app id and one of the five signed P0 ecosystems
  (`flatpak_flathub`, `apt_deb`, `pacman`, `dnf_rpm`, `rootless_podman_oci`);
- an access mode of `read_only` by default, or `explicit_write` only with a
  bounded `review_ack`;
- 1–16 pathless permission labels and 1–8 upstream mechanism ids;
- a `SourceClaim` with `source_id`, upstream `provenance`, `signature`,
  `verified` and `scope: guest-only`;
- six exact-boolean host facts, a `guest_class` of `SYNTHETIC` or
  `REAL_GUEST_NOT_RUN`, and `no_paid_tiers`, `no_telemetry`, `no_accounts`
  flags.

Exact types are enforced: `bool` is not an `int`, `str` subclasses and bytes
are not accepted where an exact `str` is required, and duplicate JSON keys,
non-finite constants, hostile Unicode and huge integers fail closed. No field
carries a filesystem path, URI, command or argument vector.

### Provenance and signature gating

Provenance and signature are requirements, not observations. The five P0
ecosystem rules mirror the in-flight sources contract as bounded plain data;
this package does **not** import that unmerged module:

| Ecosystem | Allowed provenance | Signature |
| --- | --- | --- |
| `flatpak_flathub` | `official-flathub`, `distribution-flatpak` | `gpg` |
| `apt_deb` | `ubuntu-archive`, `debian-archive` | `apt-signed-by` |
| `pacman` | `arch-official` | `pacman-key` |
| `dnf_rpm` | `fedora-official` | `rpm-gpg` |
| `rootless_podman_oci` | `official-registry`, `verified-image` | `cosign`, `sigstore` |

A request passes only when the claimed source id matches its ecosystem, the
claim is `verified` with `guest-only` scope, **and** the caller's synthetic
facts say `signature_verified` and `source_verified`. These facts are fixture
inputs, not a signature check: no GPG, rpm, apt, cosign or Sigstore verifier
runs here. Real verification belongs to a separately reviewed host adapter
and real-guest acceptance, neither of which exists in this change.

### Decision vocabulary

- `DESCRIBE_ONLY` — valid synthetic request; returns inert `UPSTREAM ...`
  steps ending in `REVIEW_REQUIRED before any real-guest launch or write grant`.
- `REFUSE` — hostile input, host context, untrusted or unsigned claim,
  forbidden permission, non-upstream mechanism, duplicate service, core
  mutation claim, or a non-FOSS condition.
- `NOT_RUN` — `REAL_GUEST_NOT_RUN`; reasons `REAL_GUEST_BLOCKED` and
  `GUEST_NOT_RUN`; no steps are emitted.

`launch_permitted` is derived to `False` on every decision, and
`guest_acceptance` is always `NOT_RUN`. Even a reviewed `explicit_write`
request only produces a description; promotion to a real guest is not
implemented or authorized here.

### Forbidden by construction

`FORBIDDEN_PERMISSIONS` includes `core_mutation`, `privileged`, `always_on`,
`host_root`, `host_socket`, `device_access`, `unrestricted_network`,
`host_home_write`, `duplicate_sandbox`, `duplicate_compositor`,
`duplicate_service`, `telemetry`, `paid_tier` and `account_required`. The
top-level no-paid/no-telemetry/no-account flags are mandatory exact `true`
values; a request that omits or falsifies them is refused before any other
gate. There is no billing, analytics, account, activation, ad or credential
code in this package.

## Synthetic verification

Fixtures live in `scratch/lacos_app_isolation/fixtures/` and are generated
deterministically by `tools/lacos_app_isolation/generate_fixtures.py`:
three positive descriptions, fourteen negative decisions and two hostile raw
documents, with SHA-256 pins in the fixture `SHA256SUMS`.

```sh
python tools/lacos_app_isolation/generate_fixtures.py
PYTHONPATH=. python -m unittest discover -s tools/lacos_app_isolation -p 'test_*.py'
python tools/lacos_app_isolation/run_contract_checks.py
```

- `test_app_isolation_contract.py` — 20 unittest cases covering canonical
  digests, every gate, bounds, hostile documents and fixture hash pins.
- `run_contract_checks.py` — static AST invariants (no process/network/write
  imports or calls, no duplicate-stack identifiers, no absolute path
  literals), 19 fixture hash pins, all decision gates, real-guest block,
  owned-path diff proof, and deterministic evidence with a `.sha256` sidecar.
- Evidence: `scratch/lacos_app_isolation/evidence/evidence_synthetic.json`
  (`label=SYNTHETIC`, `real_guest.status=BLOCKED`, `real_guest.gate=NOT_RUN`)
  plus `evidence_synthetic.json.sha256`.

Tests are intentionally inside the owned tooling directory because `tests/`
is outside this change's ownership. CI coverage of this module is `NOT_RUN`;
only host-local synthetic runs are claimed.

## Resource / evidence note

- **Measured (`SYNTHETIC`):** host-local unit-test and verifier wall time
  (well under one second on the authoring host), bounded documents (≤ 1 MiB),
  at most 16 permissions and 8 mechanism steps per decision. Static analysis
  counts zero process launches, sockets, file writes or background services
  in the owned production modules.
- **Not measured (`NOT_RUN`):** real Flatpak/bubblewrap namespace setup,
  portal prompts, systemd scope/unit behavior, rootless Podman runtime,
  actual guest RSS/CPU/GPU, screen-reader announcements (no UI or
  announcements are added) and any real application launch.
- The contract deliberately makes no stability, security, accessibility or
  approved-visual tradeoff: it is pure Python with no service, polling loop,
  compiled input or visual asset.

## Limitations and residual gates

- This is a foundation contract, not an isolation implementation. There is no
  guest probe, portal wiring, systemd adapter, permission UI, policy daemon,
  signature verification, compositor change or package integration.
- A separately reviewed host adapter and a disposable real guest must prove
  upstream mechanisms actually confine each app before any capability can be
  treated as operational trust.
- Integration requires independent review and a distinct human approving
  review; this work remains an open draft PR with no self-approval or merge.
