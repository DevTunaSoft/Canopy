# PE-068 desktop focus/session recovery after shell restart

Status: **implemented, pure source contract; host is not wired**. Base and
requested exact tip: `ea2b92fa034c598a16fb856169d0a00cb5e0e09f`
(`integration/canopy-classic-20261123`). Owned paths are exactly three:

- `canopy_features/reliability/desktop_focus_recovery_contract.py` (new)
- `tests/test_pe068_desktop_focus_recovery_contract.py` (new)
- `docs/DESKTOP_FOCUS_RECOVERY_CONTRACT.md` (this note)

No compiled C++/QML, approved art, workflow, protected file, credential, VM or
`main` path is touched. No shell is restarted, no window is focused and no PR
is merged here.

## Purpose and boundary

`Reconciler` is a single-thread, bounded decision surface for the trusted host
loop. It answers one narrow question: after the host has reported a
recovery-required state, has it also reported an active session and a
non-empty window set *in that order*? If so the view offers
`offer_restore`; otherwise it stays `no_restore`. An offer is **not** focus
actuation, shell startup, desktop observation or release acceptance. The view
hardcodes `focus_actuated`, `window_focused`, `shell_running`,
`desktop_session_started`, `mint_acceptance_proven`, `owner_visual_approval`
and `measurement_performed` to `False`.

No I/O, clock, randomness, timer, polling, thread, socket, process, D-Bus, Qt,
environment read or filesystem access is performed. Inputs are already-delivered
immutable `HostEvent` values; `from_host_event` only projects them. The module
never emits or subscribes.

## Reuse of the existing event contract

`docs/HOST_EVENT_CONTRACT.md` is the authority. This module adds **no** topic,
field, payload shape or protocol version to that primitive and imports its
envelope directly. It reads exactly three existing v2 topics and their
already-documented scalar fields:

| Existing topic | Field(s) | Projected kind |
| --- | --- | --- |
| `capabilities.report` | `needs_recovery`, `has_active_pack` (plus the fixed report status/schema/count fields) | `restart` / `cleared` |
| `session.state.changed` | `state` | `session_active` / `session_inactive` |
| `window.state.changed` | `window_count` | `windows_ready` / `windows_empty` |

`needs_recovery=True` together with `has_active_pack=True` is contradictory
and is refused. A missing required field becomes `unavailable`, never an
invented `False` or `0`. A generic `source` provenance string must match the
caller's declared source; unknown fields, wrong scalar types, unbounded text,
bad sequences, wrong topics and wrong protocol versions fail closed with
`RecoveryContractError` and leave committed state unchanged.

## State machine

Committed statuses: `cold` (default), `awaiting_session`, `awaiting_windows`,
`deferred`, `restore_ready`.

1. Only a host `restart` observation leaves `cold`. Pre-restart session/window
   facts are redundant and cannot describe the restarted desktop.
2. After restart, a session fact newer than the restart is required. An
   inactive (`locked`/`suspended`) session defers recovery permanently until a
   new `session_active` fact arrives.
3. A window fact must be newer than the accepted `session_active` fact to
   unlock `restore_ready`; an older window list is not proof of a current
   focus target. `window_count=0` defers.
4. `cleared` returns to `cold`; a fresh `restart` resets all prior readiness.
5. Duplicate fingerprints are ignored (`DUPLICATE`), lower/equal sequences are
   refused (`STALE`), and facts that do not change status are `REDUNDANT`.
   Rejected facts consume no dedup slot. Only `TRANSITION` advances the
   transition count and retained history (at most 16 outcomes).

Dedup and history are bounded (64 and 16 entries), every view is immutable,
duplicate and stale replays cannot regress state, and equal inputs produce
equal view bytes.

## Evidence — SYNTHETIC / NOT_RUN

Environment: Windows 11, Python 3.14.10, pure-Python targeted tests. No Qt
build, Mint guest, live desktop, real shell restart or window manager was
used. Full suite was **not** run; only the targeted and adjacent patterns
below were executed.

| Check | Command | Result | Log SHA-256 |
| --- | --- | --- | --- |
| RED (module absent) | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_pe068_desktop_focus_recovery_contract.py'` | rc=1, import error | `744e77a9065cf3556037769d555b96a27f7d36e2b75757c77cfa38eb16c59f70` |
| GREEN (41 tests) | same command after implementation | rc=0, `Ran 41 tests ... OK` | `0918ef461b6809102ad52216342bb22487d6ba9b70215f6e927fd168354ab655` |
| Adjacent host-event tests | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_*host_event*.py'` | rc=0, 37 tests OK | `147613b3ed777489682a23f6c0421020e30a61774637b29bca3a06f31f06b8b5` |
| Adjacent network contract | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_c100_reliability_network_reconnect_contract.py'` | rc=0, 30 tests OK | `5cfde312017429622e6c7a05368e201d006b681f71c6ce09046b3289606ee499` |
| Adjacent session lifecycle | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_c100_reliability_session_lifecycle_snapshot.py'` | rc=0, 23 tests OK | `2aaeb85004accedc239d68cf888a12c6b6bc8227d460de79025a1948ce893bfd` |
| Mutation sensitivity | disabled the contradictory-flag guard, ran the target, restored exact bytes | rc=1, one expected failure; restored SHA-256 equals original `53c55b44608a986c65a7086d04660a437eff687093454cfc2d12573c39945786` | `d9b64dc852e5dd41bc2b854c272dcb330c33825ebf500ad1dcb016c6679e8a94` |

Raw logs, return codes, the machine-readable ledger and a `SHA256SUMS`
manifest live in `scratch/master_directive_20261126/evidence/session_recovery_contracts/`
under the main repository (untracked scratch evidence, not part of the patch).

### Resource impact

- Measured: `SYNTHETIC` Python unit checks only. No sustained idle PSS/CPU
  sampling and no timing claim is made.
- `NOT_RUN`: real-Mint idle PSS/CPU, compositor wakeups, live shell restart,
  real window-manager focus changes and any guest acceptance run.
- Screen-reader behavior is unchanged: the module creates no UI, announcement
  or accessibility metadata; it only exposes enumerated tokens to callers.
- Bounded by construction: one frozen view, at most 64 dedup fingerprints and
  16 retained outcomes, no polling, thread, daemon, unbounded cache or
  transport. No stability, security, accessibility or approved visual quality
  is traded for a minor resource gain.

### Honest limits

- This is a source contract. The compiled Classic shell is not wired and keeps
  its existing fail-closed behavior; a trusted host must separately deliver
  the three event facts. No event is probed or emitted here.
- No real session, VM, credential, protected-file edit, visual/asset edit,
  Mint acceptance, owner visual approval or merge authorization is claimed.
