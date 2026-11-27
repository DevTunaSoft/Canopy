# Network reconnect status contract (PE-053)

## Scope and ownership

Base: `c6de24153eef0b58f921a8bffdaeaa8033288a75` (exact requested tip).
Worktree: `C:/Users/X1/AppData/Local/Temp/pe053-network-c6de241`.
Branch: `fix/network-reconnect-c6de241`. Draft PR target:
`integration/canopy-classic-20261123`. No merge is performed.

Exactly three owned paths change:

- `canopy_features/reliability/network_reconnect_contract.py` (new)
- `tests/test_c100_reliability_network_reconnect_contract.py` (new)
- `docs/NETWORK_RECONNECT_CONTRACT.md` (this note)

Not touched: `canopy_core/host_events.py`, `docs/HOST_EVENT_CONTRACT.md`,
`canopy_features/system/quick_controls_state.py`, compiled C++/QML, approved
art, workflows, credentials, network configuration or any other agent's files.

## Contract

A pure, single-thread reconciler consumes trusted network facts already
delivered through the existing host-event boundary: protocol v2
`capabilities.report` and its documented `network_connected` bool field. It
adds no event topic, no host-event field name and no UI token.

Observation kinds are fixed: `connect`, `disconnect`, `unavailable`.
Committed status tokens are fixed: `unknown`, `unavailable`, `disconnected`,
`reconnected`, `connected`.

| From | Observation | To |
|---|---|---|
| `unknown` | `connect` | `connected` |
| `unknown` | `disconnect` | `disconnected` |
| `unknown` | `unavailable` | `unavailable` |
| `disconnected` / `unavailable` | `connect` | `reconnected` |
| `reconnected` / `connected` | `connect` | `connected` |
| any | `disconnect` | `disconnected` |
| any | `unavailable` | `unavailable` |

`reconnected` is emitted only for the first trusted connect after an outage;
steady connectivity settles back to `connected`. A missing network field is
`unavailable` (no guessed `False`), a wrong-typed field fails closed. Duplicate
fingerprints are ignored, stale or conflicting sequences cannot regress
committed status, and rejected events consume no dedup slot. History and dedup
are bounded; `close()` releases them and refuses later observations.

Views are immutable. Their UI projection is restricted to the already
documented quick-controls network tokens (`connected`, `disconnected`,
`unknown`); `availability` is `AVAILABLE` only for connected/reconnected and
`UNAVAILABLE` otherwise. It is a display-level connectivity view, not a
control grant. `to_event_payload()` uses only the existing field names
`status`, `source` and `network_connected`, omits the fact for
`unknown`/`unavailable`, and must be emit-able on the existing bus.

Safety boundary: no sockets, network access, timers, polling, threads,
processes, credentials, environment reads, clock, Qt, D-Bus or filesystem I/O.
No live host fact is probed or invented.

## Evidence — SYNTHETIC / NOT_RUN

Environment: Windows 11, Python 3.14.9, pure-Python targeted tests. No Qt
build, Mint guest, live desktop or network interface was used. Full suite was
not run; only the targeted and related patterns below were executed.

| Check | Command | Result | Log SHA-256 |
|---|---|---|---|
| RED (module absent) | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_c100_reliability_network_reconnect_contract.py'` | rc=1, `ModuleNotFoundError` | `d5e3b70177119b9777d6be4518b87e163348a68b67888ba15ab29b0c8461951f` |
| GREEN (30 tests) | same command after implementation | rc=0, `Ran 30 tests ... OK` | `e4b65ff09f004bf46ce771d5e7bd4aebf18a6e3c9fdd2409dd96679e6a7bd91a` |
| Related host-event tests | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_*host_event*.py'` | rc=0, 37 tests OK | `e039745776fb59d277450cd29c80f02f5a64b57466f26fb33c700a9f9c1ab63c` |
| Related reliability tests | `PYTHONPATH=. python -m unittest discover -s tests -p 'test_c100_reliability_*.py'` | rc=0, 254 tests OK | `58992820633a48f837167a202d6aea29722bdfbdabd143aac00ae5f75f86337b` |
| Mutation sensitivity | scratch script flips the reconnect guard, runs the targeted tests, restores bytes | rc=1, 6 expected failures; restored SHA-256 equals original | `ddd9a3f4b1ff807f81fbd9d1bca96746bae2b9ea5d8a3bab9eb51b0e78f34ee3` |

### Resource impact

- Measured: `SYNTHETIC` Python unit checks only. No sustained idle PSS/CPU
  sampling and no timing claim is made.
- `NOT_RUN`: real-Mint idle PSS/CPU, compositor wakeups, NetworkManager
  behavior, live disconnect/reconnect events and screen-reader output.
- Screen-reader behavior is unchanged: the module creates no UI, announcement
  or accessibility metadata; only enumerated tokens are exposed to callers.
- Bounded by construction: one frozen status view, bounded dedup/history
  (at most 64 entries each), no polling, thread, daemon, cache growth or
  transport. No stability, security, accessibility or approved visual quality
  is traded for a minor resource gain.

### Honest limits

- This is a pure contract: the compiled Classic shell is not wired and still
  uses its existing fail-closed behavior. A trusted host must separately
  supply observations; none are probed here.
- No real network change, credential, protected-file edit, visual/asset edit,
  Mint acceptance, owner visual approval or merge authorization is claimed.
