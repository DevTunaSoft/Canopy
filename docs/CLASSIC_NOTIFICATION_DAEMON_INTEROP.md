# Classic native daemon interop contracts (pure Python)

This document describes one **nonvisual, pure-Python** slice of native
notification daemon interoperability at the existing trusted source boundary.
It is a contract and probe surface only: it is not a compiled Qt bridge, not a
transport client, not a daemon and not a live desktop notification source.

## Scope and ownership

Exactly three new paths are owned by this change:

- `canopy_features/notifications/daemon_interop.py`
- `tests/test_c100_notification_daemon_interop.py`
- `docs/CLASSIC_NOTIFICATION_DAEMON_INTEROP.md`

No existing file is edited. Nothing here modifies QML, compiled inputs,
approved artwork, workflows, the trusted host-event bus, the existing
[`host_event_source.py`](../canopy_features/notifications/host_event_source.py),
the notification
[`host_snapshot_producer.py`](../canopy_features/notifications/host_snapshot_producer.py),
or the separately owned delivery-lifecycle module. No host-event topic, payload
field or protocol version is added, so
[`HOST_EVENT_CONTRACT.md`](HOST_EVENT_CONTRACT.md) is unchanged.

## What the contract does

`NotificationDaemonInterop` is a read-only availability view over one trusted
source. It accepts either the existing `TrustedHostEventSource` or the existing
`HostSnapshotProducer`; a source must be an exact trusted type and report
`connected() is True` at construction or reattach. A self-owned source is used
when none is injected and is closed only by `close()`.

Two bounded, host-only probes decide the state:

| Probe | Input | Result |
|---|---|---|
| Source loss | one `connected()` read from the trusted source | `source_live` / `source_lost` |
| Capability | one bounded host observation mapping | `capability_present` / `capability_absent` |

The capability observation must be a `Mapping` with exactly the keys
`capability` and `available`, where `capability` is the exact token
`native_notification_daemon` and `available` is the exact boolean `True`.
Wrong containers, extra or missing keys, wrong field types, hostile mapping
dunders, oversized tokens, unsafe code points and unknown tokens are all
refused. No value from a refused observation is echoed.

`probe()` runs both probes in one bounded cycle. `state()` is a pure read of
the last probes; it does no work and never mutates. `InteropState` is frozen
and `as_dict()` returns a fresh copy.

`available` is reported only when a live source probe, a present capability
probe, no recorded loss, no refusal and an explicit non-closed lifecycle
coincide. Every other path is `unavailable` with a fixed reason.

| Bound | Value | Enforced on |
|---|---|---|
| Total probe budget | 1..16 (`MAX_PROBES`) | constructor; every probe call spends one unit |
| Observation fields | 1..8 (`MAX_CAPABILITY_FIELDS`) | `probe_capability` |
| Capability token | <= 64 UTF-8 bytes (`MAX_TOKEN_BYTES`), exact token | `_validate_observation` |
| Recorded view | seven fixed scalars; no history structure | `InteropState` |
| Refusal tokens | four fixed strings | `INVALID_CAPABILITY`, `INVALID_SOURCE`, `INTEROP_CLOSED`, `PROBE_LIMIT` |

A lost source is sticky: a later capability probe cannot restore availability.
Recovery requires `reattach()` with a fresh trusted, connected source followed
by a new capability probe. Budget exhaustion and explicit close are likewise
fail-closed. No probe, state or reattach call starts a service or leaves the
process.

## Negative-control table (`SYNTHETIC`)

Every row is a deterministic synthetic probe in
[`tests/test_c100_notification_daemon_interop.py`](../tests/test_c100_notification_daemon_interop.py).
A rejection means a fixed refusal token and an `unavailable` state; no caller
text, exception message or partial observation is published.

| Control | Synthetic input | Expected outcome | Test |
|---|---|---|---|
| Missing capability | `probe()` with no observation | `unavailable` / `capability_absent` | `test_probe_without_capability_stays_unavailable` |
| Foreign token | `capability="other"`, upper-case token, padded token | fixed `INVALID_CAPABILITY_OBSERVATION` | `test_capability_token_must_be_exact` |
| Wrong acknowledgement | `available` is `False`, `1`, `"True"`, `None`, `[]` | refused; exact `True` required | `test_capability_available_flag_must_be_exact_true` |
| Extra or missing key | added `extra`; deleted `capability` or `available`; empty mapping | whole observation refused | `test_extra_or_missing_capability_field_is_refused` |
| Wrong container | `None`, `str`, `bytes`, `int`, `list`, `tuple`, `frozenset` | refused with domain token | `test_wrong_observation_container_is_refused` |
| Hostile mapping | finite mapping raising from `__getitem__`, `__iter__` or `__len__` with a secret marker | fixed refusal; marker absent from state | `test_hostile_mapping_never_echoes_secret` |
| Oversized token | 65-byte token | refused | `test_oversized_capability_token_is_refused` |
| Source loss | injected source closed after an available state | `unavailable` / `source_lost`, capability cleared, loss counted | `test_source_loss_fails_closed_and_clears_capability` |
| Hostile liveness | `connected()` raises with a secret marker | bounded loss; marker absent from state | `test_hostile_source_connected_probe_is_a_loss` |
| Non-boolean liveness | `connected()` returns `1`, `"yes"`, `[]`, `None`, `0` | bounded loss | `test_non_true_source_connected_result_is_a_loss` |
| Budget exhaustion | `max_probes=2`, third probe | `unavailable` / `probe_limit`, count stays 2 | `test_probe_budget_is_bounded_and_fails_closed` |
| Bad reattach | foreign object, string, disconnected trusted source | `DaemonInteropError` | `test_reattach_requires_a_trusted_live_source` |
| Reattach recovery | fresh trusted source after loss | still unavailable until a new capability probe | `test_reattach_clears_loss_but_requires_new_capability_probe` |
| Close | double `close()`, then probes | `unavailable` / `closed`; probes refused | `test_close_is_explicit_unavailable_and_idempotent` |
| Ownership | injected source then `close()` | injected source stays connected | `test_injected_source_is_not_closed_by_interop` |
| Trusted composition | injected `HostSnapshotProducer` | accepted as source; available after probes | `test_snapshot_producer_is_an_accepted_trusted_source` |
| Invalid bounds / source | `0`, `17`, `True`, `"3"`, `1.0`, foreign or dead source | `DaemonInteropError` at construction | `test_invalid_probe_bounds_are_rejected`, `test_invalid_or_disconnected_source_fails_closed` |
| Immutability | frozen state assignment; mutate `as_dict()` copy | state unchanged | `test_state_is_frozen_and_snapshot_is_a_fresh_copy` |
| Source integrity | AST import and literal scan | no transport/execution import, no new topic literal, no external launch token | `test_no_transport_or_execution_imports`, `test_no_new_topic_or_side_effect_literals` |

## Non-behaviour (deliberately absent)

No D-Bus, socket, daemon, process, timer, polling, thread, filesystem read or
write, environment access, Qt import or external notification service. The
contract does not assert that a daemon is running, does not request a desktop
announcement, and does not change the Classic panel's disconnected disclosure.
No permission, launch, focus, sound, screen-reader announcement or visual
change is implied. Wiring into a compiled host adapter remains
`AWAITING_WIRING`.

## Verification and evidence labels

Run from the repository root:

```sh
python -m unittest tests.test_c100_notification_daemon_interop -v
```

All 23 tests are **SYNTHETIC** contract tests: trusted in-process sources for
positives and finite hostile callers for negatives. The targeted and related
notification suites are **SYNTHETIC** or **CI-SCOPED** evidence only. Real live
notification delivery, Linux Mint acceptance, screen-reader behaviour and owner
visual approval are **NOT_RUN**. No maturity level above the existing UI /
contract level is claimed.

### Resource impact

- **SYNTHETIC:** 23 targeted contract tests plus 81 neighboring
  notification/event/host-event tests; seven fixed scalars in one frozen
  record, a 16-call probe budget and no retained history. No daemon, transport,
  poll, timer, thread or file I/O was started; no runtime memory number is
  claimed.
- **NOT_RUN:** real Mint desktop PSS/CPU, compiled Qt self-tests, live
  notification delivery and screen-reader announcement.
- **screen-reader:** NOT_RUN — no UI, announcement or accessibility surface is
  touched.
- The contract reads only bounded trusted state and trades no stability,
  security, accessibility or approved visual quality for a minor gain.
