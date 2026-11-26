# Classic notification host snapshot producer (pure Python)

This document describes one **nonvisual, pure-Python** slice of the
notification host snapshot bridge described in the offline
`disconnected_feature_specs_af97e11.md` (Spec 1). It is not a compiled Qt
bridge, not a notification daemon and not a live desktop notification source.

## Scope and ownership

Exactly three new paths are owned by this change:

- `canopy_features/notifications/host_snapshot_producer.py`
- `tests/test_c100_notification_host_snapshot.py`
- `docs/CLASSIC_NOTIFICATION_HOST_SNAPSHOT.md`

Nothing here modifies `prototype/classic/main.cpp`, `CMakeLists.txt`, QML,
approved artwork, workflows, the trusted host-event bus, the existing
[`host_event_source.py`](../canopy_features/notifications/host_event_source.py)
or any other agent's file. The compiled C++ bridge, its fixture and its flag
remain a separate workstream; this module only supplies a proven, bounded
producer that such a bridge could consume later.

## What the producer does

`HostSnapshotProducer` is a read-only view over one trusted
`TrustedHostEventSource`:

- with no events, `snapshot()` has **zero rows**;
- `publish(topic, payload)` is an explicit host-only call that emits a real
  `HostEvent` on the existing bus — it never fabricates a notification, topic
  or payload;
- `compose(records)` projects the source's bounded records into one frozen
  wire-format snapshot; the whole input is validated before any row is
  returned;
- any rejected input fails closed: `snapshot()` returns empty rows and a fixed
  `refusal` token, never a partial, plausible-looking list.

The four accepted topics are exactly the v2
[host event contract](HOST_EVENT_CONTRACT.md) set, byte-identical as a set to
the [Classic notification centre](../prototype/classic/NotificationCenter.qml)
`contractTopics`: `app.catalog.changed`, `window.state.changed`,
`session.state.changed`, `capabilities.report`. There is no fifth topic and no
dynamic registration.

Wire format (`to_json_bytes()`, deterministic `sort_keys`, ASCII, compact
separators):

```json
{"records": [{"body": "item_count=3", "id": "host-events:app.catalog.changed:1",
              "source": "host-events", "title": "Application catalogue updated",
              "topic": "app.catalog.changed"}], "source": "host-events"}
```

| Bound | Value | Enforced on |
|---|---|---|
| Records | 0..12, newest first | `MAX_RECORDS` / `max_records` |
| Whole JSON | <= 64 KiB | `MAX_JSON_BYTES` / `max_bytes` |
| `id` | 1..64 UTF-8 bytes, unique | `_bounded_text` + seen-id set |
| `title` | <= 120 UTF-8 bytes | `_bounded_text` |
| `body` | <= 280 UTF-8 bytes | `_bounded_text` |
| `source` | exactly `host-events` | `_validate_record` |
| `topic` | one of the four approved topics | `_validate_record` |
| Text safety | no control/format/surrogate/private-use/noncharacter code points | `_UNSAFE_CATEGORIES` |
| Record keys | exactly `{id, title, body, source, topic}` | `RECORD_KEYS` |

`HostSnapshot` and its records are frozen dataclasses; `as_dict()` returns a
fresh copy on every call, so a caller cannot mutate a later snapshot.

## Non-behavior (what is deliberately absent)

No D-Bus, socket, daemon, process spawn, timer, polling, thread, filesystem
read/write, environment access, Qt import or external notification service.
No permission, launch, focus, sound, screen-reader announcement or visual
change is implied. The compiled shell still uses its existing disconnected
source by default (zero rows plus the `Unavailable —` disclosure).

## Verification and evidence labels

Run the synthetic suite and the foundation check from the repository root:

```sh
python -m unittest tests.test_c100_notification_host_snapshot -v
python tools/check_foundation.py
```

All 34 tests are **SYNTHETIC** contract tests: they use real in-process
`HostEvent` deliveries for positive cases and synthetic record dictionaries
for validator controls; they never fabricate a `HostEvent`. The targeted
suite and any offscreen/compiled fixture are **SYNTHETIC** or **CI-SCOPED**
evidence only. Real live notification delivery, Linux Mint acceptance,
screen-reader behavior and owner visual approval are **NOT_RUN**. No maturity
level above the existing L3 UI / L2 contract is claimed here; the compiled
producer-to-adapter path is `AWAITING_WIRING`.
