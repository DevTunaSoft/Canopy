# Classic quick controls — bounded audio/network/power status contracts (PE-099)

## Scope and ownership

Base: `60809aef3dd2473ecd133ed8d3c5ef8316b19065` (integration tip of
`integration/canopy-classic-20261123`, merge of PR #700). Worktree:
`C:/Users/X1/AppData/Local/hermes/cache/scratch/pe099_wt_60809ae`, branch
`feat/quick-controls-status-contracts-pe099-60809ae`.

Exactly three owned paths change:

- `canopy_features/quick_controls/status_contracts.py` (new)
- `tests/test_pe099_quick_controls_status_contracts.py` (new)
- `docs/CLASSIC_QUICK_CONTROLS_STATUS_CONTRACTS.md` (this note)

Not touched: compiled `main.cpp`, CMake, QML, images/assets, workflows,
AGENTS.md, other agents' producer work, and the paths owned by PRs
#699/#700/#701/#703/#704 (session-controls-native, notification-daemon,
launcher-enumeration, config-schema-migration and dock-running-indicator
modules, their docs and tests). No merge, promotion, approval or visual change
is claimed; the PR stays draft.

## What this contract is

A narrow, fail-closed projection at the **existing trusted source boundary**.
It consumes only:

- an already-validated
  `canopy_features.quick_controls.host_status_producer.HostStatusSnapshot`
  (the trusted host's `network_connected`, `volume_percent` and
  `battery_charging` facts on the existing `capabilities.report` topic), and
- `canopy_features.system.quick_controls_state.Observation` records that supply
  the audio mute status (`muted` / `unmuted`).

It emits immutable per-domain records for exactly `audio`, `network` and
`power`, using the **existing** `STATUS_TOKENS` and `STATUS_LABELS` vocabulary
with an import-time guard against vocabulary drift. No new event topic, wire
field, UI token, disclosure, transport or control action is introduced. The
session domain stays out of scope.

API:

- `from_snapshot(snapshot, *, observations=())` — project a trusted producer
  snapshot plus trusted audio observations.
- `from_payload(payload, *, source, observations=())` — project a trusted
  source mapping through the existing `host_status_producer.from_payload()`
  gate; topic, provenance and field types are validated there, not redefined.
- `unavailable(*, source)` — explicit revocation of all three domain statuses.
- `StatusSnapshot.record(domain)`, `.to_dict()` (fresh read-only mapping),
  `.to_json_bytes()` (deterministic compact ASCII JSON, 4 KiB cap) and
  `.as_observations()` (existing `Observation` objects for observed domains).

Fail-closed rules:

- Missing facts stay `unknown`; never `False`, `0`, a label inference or a
  previous reading. Volume `0` is **not** treated as a mute fact.
- Provenance is explicit and reused from the producer allowlist
  (`host-events`, `host-status-file`). Every audio observation must agree with
  the aggregate source; an absence event cannot coexist with an observation.
- Only audio observations are owned; network and power statuses come only from
  trusted wire facts. Duplicate observations, wrong containers/types, hostile
  provenance, unbounded detail values and oversized output all raise
  `StatusContractError` before any snapshot is returned.
- `observed` is derived from the status token; it is never caller-supplied, so
  a hostile record cannot claim an observation it does not have.

The module opens no file, starts no process, reads no environment, clock,
socket, D-Bus, device or VM, polls nothing and holds no state.

## Evidence — SYNTHETIC / NOT_RUN

Environment: Windows 11, Python 3.14.9, pure-Python contract tests. Artifacts
live at the absolute cache-scratch directory
`C:/Users/X1/AppData/Local/hermes/cache/scratch/master_directive_20261126/evidence/quick_controls_status`;
the repo-relative `scratch/master_directive_20261126/evidence/quick_controls_status`
is `ABSENT` (`sha256=null`) and is not cited as an on-disk artifact.

| Check | Command | Result | Log SHA-256 |
|---|---|---|---|
| RED before module existed | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_pe099_quick_controls_status_contracts.py'` | exit 1, `ImportError` (feature missing) | `c83ff4e82065a1932ad83fd4576fd1d4fe4d534d35610724786a6d2018a36a14` |
| Initial GREEN | same command after first implementation | 26 tests, OK | `4dab5c3be1bc2c7dfffd12ac8abca51187c790f124364229be80e6a42c0e40f3` |
| Final targeted rerun | same command after import cleanup | 26 tests, OK | `2ae102af1527679b0bf4a3ccc36e0cdbea30ed9c2341c6ae581d1c028317d2f7` |
| Related quick-controls tests | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_*quick_controls*.py'` | 110 tests, OK | `3628fd2c459a0de3550edb2457c2eeb4a290f7c177c75c7fbdf1981f2773b024` |
| Related boundary tests | `PYTHONPATH=. python -m unittest tests.test_c100_reliability_network_reconnect_contract tests.test_host_events tests.test_power_status_fallback` | 52 tests, OK | `e228e6c842ae3387b43fc18e41e434d6020dc6bc8ec7967bb499b0cccea42036` |
| Foundation check | `python tools/check_foundation.py` | PASS: foundation files, tagline, local Markdown links | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| Foundation tests | `PYTHONPATH=. python -m unittest tests.test_foundation` | 5 tests, OK | `bdb11925b424334cae611587f01499e7ae3663a0a39017ac392f6414ac07441f` |
| Mutation sensitivity | scratch probe flips the revocation/observation guard to `if False`, runs targeted tests, restores bytes | targeted rc=1, `FAIL: test_observations_cannot_coexist_with_a_revocation`; module SHA identical before/after (`cfd58f8f0c3d3e3a6184863f2754415838fefea57e1319f3d6c28669a0845605`) | `d12ceb051a2d62cae66dbc305a21f20ab089ac3986f5a060e4b5240ad53e373f` |

All numbers above are `SYNTHETIC` pure-Python evidence. `NOT_RUN`: real audio,
network and power host readings, compiled-shell status-file injection, Qt
compilation, Linux Mint acceptance, idle PSS/CPU sampling, screen-reader
output and owner visual sign-off. No full-suite claim is made here; only the
commands above were executed.

Artifact SHA-256 (file bytes):

| Artifact | SHA-256 |
|---|---|
| `canopy_features/quick_controls/status_contracts.py` | `cfd58f8f0c3d3e3a6184863f2754415838fefea57e1319f3d6c28669a0845605` |
| `tests/test_pe099_quick_controls_status_contracts.py` | `2bb382c6bbf5fa76a12da9d55d5874298560bd9bfa1e900582235e0721db5d02` |

## Resource impact

- Measured: `SYNTHETIC` Python unit checks only. No sustained idle PSS/CPU
  sampling or timing win is claimed.
- `NOT_RUN`: real-Mint idle PSS/CPU, compositor wakeups and screen-reader
  output. Screen-reader behavior is unchanged: this module emits no UI,
  announcement or accessibility metadata; it only returns immutable values.
- Bounded by construction: three immutable scalar records, at most eight
  trusted audio observations, one deterministic JSON serialization and a
  4 KiB output cap. No polling, timer, cache, thread, daemon, transport or
  retained state. Nothing here trades stability, security, accessibility or
  approved visuals for a minor performance gain.

## Honest limits

- This is a status contract only. The compiled shell is unchanged; no host
  service is read, no file is written, no control is enabled or executed.
- No real device/audio/network/VM value was probed or invented. All fixture
  values are explicitly supplied through the trusted-source contract.
- No Linux Mint acceptance, screen-reader session, owner visual approval or
  merge authorization is claimed.
