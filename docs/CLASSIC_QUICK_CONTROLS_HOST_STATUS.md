# Classic quick controls — trusted host status producer (af97e11)

## Scope and ownership

Base: `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` (integration tip of
`integration/canopy-classic-20261123`). Worktree:
`C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy_quick_status_af97e11`,
branch `feat/quick-controls-host-status-af97e11`.

Exactly three owned paths change:

- `canopy_features/quick_controls/host_status_producer.py` (new)
- `tests/test_c100_quick_controls_host_status.py` (new)
- `docs/CLASSIC_QUICK_CONTROLS_HOST_STATUS.md` (this note)

Not touched: compiled `main.cpp`, `CMakeLists.txt`, QML, assets, workflows,
notification producer files, other agents' producer work, product status
matrices/dossiers or any file outside the three above. No merge, promotion,
approval or self-approval is claimed; the PR stays draft.

## What this producer is

A pure, bounded projection of three already-supplied trusted facts — network
connectivity, audio volume and battery charging — into the wire object the
existing `QuickControlsHostStateController::applyHostEvent` already accepts.
It reuses the existing `capabilities.report` topic from
`canopy_core.host_events`; it adds no topic, field name, row, disclosure, QML
binding or control action.

API:

- `compose(*, source, network_connected=None, battery_charging=None,
  volume_percent=None)` — all arguments keyword-only; provenance has no
  default.
- `from_payload(mapping, *, source)` — projects a trusted mapping; a supplied
  `topic` must be the existing topic and a supplied `source` must agree with
  the explicit argument.
- `HostStatusSnapshot.to_dict()` — fresh read-only mapping; `to_json_bytes()`
  — deterministic compact ASCII JSON, capped at 16 KiB before return.

Wire keys are exactly `topic`, `source`, `network_connected`,
`volume_percent`, `battery_charging`. A missing fact is omitted, never
serialized as `null` and never replaced with `False`, `0` or a previous value.
Provenance is explicit: only `host-events` and `host-status-file` are accepted;
any other token (including lookalikes, case variants, control characters and
oversized or non-string values) is refused. Percentages are exact `int` values
in `0..100`; booleans are exact `bool` values; bool/int and int/float confusion
is refused. The whole input is validated before any record is built.

This module opens no file, starts no process, reads no environment, clock,
socket, D-Bus or host device, polls nothing and holds no state. The bytes are
for a trusted host to place at an explicit path; that host-side step needs
`main.cpp` ownership and is deliberately **not** done here.

## Evidence — SYNTHETIC / NOT_RUN

Environment: Windows 11, Python 3.14.9; pure-Python contract tests only.
No Qt compilation, compiled fixture, live desktop or Mint guest was used.

| Check | Command | Result | Log SHA-256 |
|---|---|---|---|
| RED before module existed | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_c100_quick_controls_host_status.py'` | exit 1, `ImportError` (feature missing) | `774fa7f77a1c0ac0e9dc7fdc7e01d99fb7b710bda35d90ea7f34ed4652ad7b7b` |
| Initial GREEN | same command after minimal implementation | 15 tests, OK | `b038a9cfb7e88ca8b8e207386e3b6f2fedccd98da3e6674ac40c47bc3bc4dd77` |
| Expanded negative controls | same command after second-job expansion | 25 tests, OK | `2da59cd45aeacb24120ecbadfe18f9a0d90fb56906da92b30933ca6ad44a08c0` |
| Final targeted rerun (post-mutation-restore) | same command | 25 tests, OK | `5526ede98b3d098a10d68789f9310837b297da280249d4745d4c8286fa7e2ec8` |
| Related quick-controls tests | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_*quick_controls*.py'` | 84 tests, OK | `e1d60b74366c8083ff58fe910444580669c1ed4d9e85d84560fce6e7d234e448` |
| Foundation check | `python tools/check_foundation.py` | PASS: foundation files, tagline, local Markdown links | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| Foundation tests | `PYTHONPATH=. python -m unittest tests.test_foundation tests.test_foundation_link_scope_guard` | 12 tests, OK | `9de4336c6a41746b1f531bf3b238b2a704ff44b4d317515c967078519b3d4b37` |
| Mutation sensitivity | scratch script mutates `<= 100` to `<= 101`, runs targeted tests, restores bytes | targeted rc=1 with `FAIL: test_volume_bounds_are_refused (value=101)`; producer SHA-256 identical before/after (`aef8ce5d68365f2fb6fbf79ecddb4ce83b0ea8483e7c471287295300c8c78a2a`) | `73e5804389f88811567c34312ac18de753abd6c01cda7f0e977e99845ca75eb3` |

All numbers above are `SYNTHETIC` pure-Python evidence. `NOT_RUN`: real host
NetworkManager/PulseAudio/UPower readings, real status-file injection into the
compiled shell, Linux Mint acceptance, idle PSS/CPU sampling, screen-reader
output and owner visual sign-off. No full-suite claim is made here; only the
targeted, related and foundation commands above were executed.

Artifact SHA-256:

| Artifact | SHA-256 |
|---|---|
| `canopy_features/quick_controls/host_status_producer.py` | `aef8ce5d68365f2fb6fbf79ecddb4ce83b0ea8483e7c471287295300c8c78a2a` |
| `tests/test_c100_quick_controls_host_status.py` | `cd3f5b9b71bf13b6aaa5861699d4c2b348378656458fca39cec24cfdeb7d13e5` |

## Resource impact

- Measured: `SYNTHETIC` Python unit checks. No sustained idle PSS/CPU sampling
  was done; timing is not claimed as a performance win.
- `NOT_RUN`: real-Mint idle PSS/CPU, compositor wakeups and screen-reader
  output. Screen-reader behavior is unchanged: this module emits no UI,
  announcement or accessibility metadata.
- Bounded by construction: one immutable record with at most three scalar
  facts, one deterministic JSON serialization and a 16 KiB byte cap. No
  polling, timer, cache, thread, daemon, transport or retained state. Nothing
  here trades stability, security, accessibility or approved visuals for a
  minor performance gain.

## Honest limits

- This is a producer contract only. The compiled shell is unchanged and still
  shows its existing fail-closed behavior; a trusted host must separately
  write these bytes to an explicit path and a separately owned compiled change
  must read them. Neither is part of this change.
- No live host value was probed or invented. Test values are synthetic
  fixtures supplied explicitly through the producer contract.
- No Linux Mint acceptance, screen-reader session, owner visual approval or
  merge authorization is claimed.
