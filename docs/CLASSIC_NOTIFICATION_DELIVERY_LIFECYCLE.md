# Classic notification delivery lifecycle (pure Python)

This document describes a **nonvisual, pure-Python** delivery contract that
composes the existing trusted notification modules. It is not a compiled Qt
bridge, a notification daemon, a live desktop notification source or a screen
reader announcement.

## Scope and ownership

Exactly three new paths are owned by this change:

- `canopy_features/notifications/delivery_lifecycle.py`
- `tests/test_c100_notification_delivery_lifecycle.py`
- `docs/CLASSIC_NOTIFICATION_DELIVERY_LIFECYCLE.md`

No existing module, host-event contract, QML file, compiled input, approved
artwork, workflow or protected file is edited. The module imports the existing
`host_event_source.py` and `host_snapshot_producer.py`; it does not reimplement
their validation or add a topic, payload field, protocol version or transport.

## What the contract guarantees

`NotificationDeliveryLifecycle` is a host-owned, single-thread view over one
`HostSnapshotProducer`. It adds the delivery/lifecycle rules that the read-only
snapshot producer does not itself expose:

| Contract | Behaviour |
|---|---|
| Bounded queue | At most `capacity` pending rows (`1..MAX_CAPACITY`, `MAX_CAPACITY = 12`, the source's own bound). Overflow evicts the oldest row and counts it; no silent drop. |
| Dedup | A projected id already present in the bounded recent-id window is counted and never enqueued twice. A replayed source view produces no second row. Distinct real events keep distinct sequence ids. |
| Fail-closed payloads | `deliver()` publishes a real host event, then admits at most one newly projected row. A bus rejection, a payload with no projected field, a hostile record, or a multi-row snapshot returns a fixed token and leaves the queue unmodified. Rejection text never echoes caller values. |
| Clear unavailable state | `status()` returns an explicit `available`/`unavailable` state plus a fixed reason (`none`, `closed`, `source_lost`, `invalid_snapshot`) and bounded counters. A closed or source-less view exposes zero rows; `take()` returns `None` and `deliver()` raises the module's domain error after close. |
| Ownership | A lifecycle that owns its producer closes it; an injected trusted producer stays host-owned. |

Fixed refusal tokens are `INVALID_NOTICE_PAYLOAD` (anything the trusted source
cannot project into exactly one notice) and `INVALID_QUEUE_RECORD` (a corrupted
queue/snapshot view). An invalid queue view also clears pending rows and is
reported as `unavailable` / `invalid_snapshot`; the next clean delivery recovers.

The wire rows keep the existing record shape `{id, title, body, source, topic}`
validated by `compose()`. `snapshot()` returns a fresh newest-first tuple;
`take()` returns a fresh oldest-first dict and removes it from the queue. Frozen
`LifecycleState` and `DeliveryOutcome` values expose only fixed tokens, ids
minted by the trusted source and bounded integers.

## Negative-control table (`SYNTHETIC`)

Every row below is a deterministic synthetic probe in
`tests/test_c100_notification_delivery_lifecycle.py`. Positive cases use real
in-process `HostEvent` deliveries; no test fabricates a `HostEvent`.

| Control | Synthetic input | Expected outcome |
|---|---|---|
| Wrong capacity | `0`, `13`, `True`, `1.0`, `"3"`, `None`, `[]`, `{}` | `NotificationLifecycleError` |
| Foreign producer | non-producer object, raw trusted source, string, int, containers | `NotificationLifecycleError` |
| Overflow | five real events into capacity 3 | 3 pending, 2 counted drops, newest first |
| Unprojected payload | `{"unrelated": "SECRET_MARKER"}` | rejected, fixed token, no caller text |
| Malformed payloads | `None`, list, string, unlisted topic, nested value, credential-like field | rejected, zero rows, no secret echo |
| Rejection recovery | bad delivery followed by a valid event | queue unchanged by the rejection; next event queues |
| Corrupt snapshot | patched producer view with a control character in `body` | `INVALID_QUEUE_RECORD`, unavailable/invalid_snapshot, no partial rows |
| Replay | patched source view that repeats a known id | rejected or duplicate, never a second row |
| Duplicate id | synthetic id added to the recent-id window | duplicate counted, row not queued |
| Queue immutability | caller mutates a returned row | internal pending rows unchanged |
| Close | `close()` twice, then `deliver()`/`take()`/`snapshot()` | unavailable/closed, zero rows, domain error on delivery |
| Injected producer ownership | close lifecycle with an injected producer | producer remains connected |
| Source loss | close injected producer | unavailable/source_lost, zero rows |
| Source integrity | AST import scan and literal scan | no transport/execution import, no new topic literal |

## Non-behaviour (deliberately absent)

No D-Bus, socket, daemon, process spawn, timer, polling, thread, filesystem
access, environment access, Qt import or external notification service. No
permission, launch, focus, sound, screen-reader announcement or visual change
is implied. The compiled shell still uses its existing disconnected source by
default (zero rows plus the `Unavailable —` disclosure).

## Verification and evidence labels

Targeted run from the worktree root (with `PYTHONPATH` pinned to that root):

```sh
python -m unittest tests.test_c100_notification_delivery_lifecycle -v
```

All cases are **SYNTHETIC** contract tests. Real live notification delivery,
Linux Mint acceptance, screen-reader behaviour and owner visual approval are
**NOT_RUN**. No maturity level above the existing L2 contract is claimed;
compiled producer-to-adapter wiring remains `AWAITING_WIRING`. No merge into
`main` is requested.
