# Native Plasma host events — bounded limiter and ceiling adaptation

This branch ports the *behavior* of PR #728's reviewed host-event limiter and
lifetime-ceiling fixes to the native Python host boundary. It does **not**
copy or compile the Classic Qt bridge: no QML, C++, icon, wallpaper, dock
geometry, compositor, transport, plugin loader or visual state is touched.
No fifth topic, payload field, protocol version, timer, poll loop, thread,
service, process, daemon or unbounded queue is added.

## Owned surface

- `canopy_core/host_events.py` — protocol-v2 bus plus a lazy limiter, a
  bounded outcome ring, a bounded catalog fingerprint ring and a one-bit
  refresh latch.
- `canopy_features/reliability/native_host_event_ceilings.py` — native
  epoch/episode ceiling records; older reliability modules are left intact,
  so their existing lifetime-cap contracts stay valid on this branch.
- `tests/test_host_event_bounded_lifetime.py`,
  `tests/test_host_event_ceiling_contracts.py` — deterministic scenarios with
  an injected clock and real `HostEvent` instances.
- `docs/NATIVE_HOST_EVENTS.md`, `scratch/native_host_events/**` — contract and
  evidence.

## Limiter contract

| Bound | Value | Purpose |
| --- | --- | --- |
| Bucket capacity | 16 | Structural; not caller-configurable |
| Refill | 1 token / 1000 ms | Monotonic clock sampled only inside `emit()` |
| Outcome history | 16 tokens | Fixed ring; no caller text |
| Catalog fingerprints | 4 | Fixed ring; no queued payloads |
| Refresh latch | 1 bit | At most one pending authoritative refresh |

The old 64-dispatch process-lifetime freeze is removed. A spaced valid event
continues indefinitely: 200 spaced events were accepted in the synthetic
scenario. A same-tick burst of 200 valid events is still delivered to trusted
callbacks; the first 16 outcomes are applied and the remaining 184 are
`*-deferred`. An exhausted bucket never turns a committed state into a
failure and never drops a legitimate event. Invalid bus input is rejected
before dispatch, spends no token and advances no sequence; topic-specific
claims remain the responsibility of the trusted consumer controllers.

A fresh `app.catalog.changed` refresh is emitted before its token is charged.
If the bucket is empty, one boolean latch carries the authoritative refresh to
the next real event that observes a token. Latch reconciliation is exempt from
a new charge because the producer work already happened. When no further
events arrive, nothing is emitted in the background: advancing an injected
clock alone changes neither the dispatch count nor the refresh count. The
17-valid-events-per-tick flood from the PR #728 audit retains every refresh:
19 latched flushes across 20 ticks plus the final flush on the next real
event gave 20 refresh requests, with rings still at 16 and 4.

## Ceiling contract

`RefreshEpochController` treats `MAX_REFRESH_EVENTS = 64` as an epoch bound.
Each accepted event makes exactly one bounded producer call; at an epoch
boundary the next real event reconciles with the current authoritative tuple,
so the newest catalog wins and no signal is frozen, queued or deferred.
Reports carry counts and fixed outcome tokens only. In the synthetic 200-event
scenario there were 200 producer calls, 3 event-driven reconciliations, a
final epoch count of 8, and a 16-entry report ring.

`EpisodeRecoveryBudget` and `EpisodeRebuildBudget` rebase grant/rebuild
budgets only on an explicit host condition (new episode or NORMAL
transition), not on a process-lifetime count or a timer. Cumulative totals are
diagnostics and never gate a grant; retained entries stay within hard caps.
The older `app_crash_contracts` and `low_memory_contracts` lifetime tests are
unmodified and remain green.

## Verification

- Foundation: `python tools/check_foundation.py` — PASS.
- Targeted (exact run): `python -m unittest tests.test_host_event_ceiling_contracts
  tests.test_host_event_bounded_lifetime tests.test_host_events
  tests.test_core_host_events_contract_v2` — 31 tests, OK.
- Scenario detail (SYNTHETIC): 10 limiter tests and 5 ceiling tests with an
  injected clock and real `HostEvent` instances; no sleeping or wall-clock
  dependence in assertions.
- Full suite: `python -m unittest discover -s tests` — 4686 tests, OK
  (skipped=49), 964.55 s on this host; log and JSON evidence in
  `scratch/native_host_events/`. Note PR #728's cited 4758 count was on its
  own larger head with 31 added test modules; this branch starts from the
  `ec910d7a` native baseline and adds 15 host-event tests.
- `NOT_RUN`: compiled Qt self-test, Mint guest, real Plasma session, screen
  reader, real transport, visual/geometry acceptance and any release gate.

## Resource impact

- Measured (`SYNTHETIC`): fixed-size accounting — two bounded deques (16 and
  4), one boolean latch, one float clock mark, a handful of fixed counters,
  one immutable result token; each emit performs O(1) ring work and one clock
  sample. Python test counts above were measured on the Windows host.
- Deliberately not measured (`NOT_RUN`): shell-owned PSS/CPU, compiled Qt
  frame timings, monitor signal rates, full-suite timing deltas and real
  desktop behavior. The change removes a dead lifetime branch and adds no
  timer, thread, animation, service, polling or repeated rendering, so it
  does not trade stability, security, accessibility or approved visuals for a
  minor gain.
- Screen reader (`NOT_RUN`): no announcement source or accessibility label is
  added or changed.
