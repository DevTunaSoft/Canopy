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
  returned, and any rejected record raises `SnapshotProducerError` rather
  than a built-in exception (including hostile mapping/built-in failures);
- any rejected input fails closed: `snapshot()` returns empty rows and a fixed
  `refusal` token, never a partial, plausible-looking list. Rejection messages
  are fixed strings: a hostile value or its exception text is never echoed or
  chained into the snapshot surface.

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

## Negative-control table (`SYNTHETIC`)

Every row is a deterministic synthetic probe in
[`tests/test_c100_notification_host_snapshot.py`](../tests/test_c100_notification_host_snapshot.py).
A rejection means either `compose()` raises `SnapshotProducerError` or the
producer returns zero rows with a fixed `refusal` token; no partial list is
ever published.

| Control | Synthetic input | Expected outcome | Test |
|---|---|---|---|
| Unapproved topic | `topic="wifi.scan.changed"` | whole input rejected | `test_unapproved_topic_is_rejected` |
| Foreign source | `source="dbus"` | whole input rejected | `test_foreign_source_is_rejected` |
| Control character | `body="status=ok\nhidden"` | whole input rejected | `test_control_character_in_body_is_rejected` |
| Bidirectional override | `title="\u202ereport"` | whole input rejected | `test_bidirectional_override_in_title_is_rejected` |
| Wrong field type | `body` is `7`, `True`, `None`, `[]` or `{}` | whole input rejected; no raw `TypeError` | `test_non_string_record_field_is_rejected` |
| Unhashable mapping key | synthetic `Mapping` whose key iteration yields a `list` | `compose()` raises `SnapshotProducerError`, never a raw `TypeError`; `snapshot()` keeps zero rows and the fixed refusal token | `test_unhashable_mapping_key_is_rejected_with_domain_error`, `test_unhashable_mapping_key_snapshot_fails_closed` |
| Hostile mapping lookup | synthetic `Mapping` whose `__getitem__` raises `RuntimeError("hostile lookup SECRET_MARKER")` | fixed `SnapshotProducerError`; no built-in error or secret text in the message | `test_hostile_mapping_lookup_leaks_no_builtin_or_secret` |
| Surrogate code point | `title="\ud800hidden"` | rejected with `SnapshotProducerError`, never a raw `UnicodeEncodeError`; no echoed value | `test_surrogate_in_record_field_is_rejected_with_domain_error` |
| Hostile source exception | source `snapshot()` patched to raise `RuntimeError("SECRET_MARKER")` | zero rows, fixed refusal token, recovery on next clean read; no secret text | `test_source_exception_snapshot_fails_closed_without_echo` |
| Extra or missing key | added `extra`; deleted `topic` | whole input rejected | `test_extra_record_key_is_rejected`, `test_missing_record_key_is_rejected` |
| Wrong container type | `str`, `bytes`, mapping, `frozenset`, `None`, `int`, `bool` | whole input rejected | `test_unexpected_record_collection_type_is_rejected` |
| Wrong entry type | `None`, `str`, `int`, `list`, `bool` entry | whole input rejected | `test_non_mapping_record_entry_is_rejected` |
| Late bad record | valid record followed by a foreign-source record | no partial rows | `test_bad_later_record_rejects_the_whole_input` |
| 13th row | `MAX_RECORDS + 1` records | whole input rejected | `test_thirteenth_record_is_rejected` |
| Oversized id / title / body | 65 / 121 / 281 bytes | whole input rejected | `test_id_over_64_bytes_is_rejected`, `test_title_over_120_bytes_is_rejected`, `test_body_over_280_bytes_is_rejected` |
| Multibyte byte bound | 61 two-byte characters in `title` | rejected at 122 bytes | `test_field_bounds_count_utf8_bytes` |
| JSON byte cap | one valid record with `max_bytes=1` | whole input rejected | `test_json_byte_cap_is_rejected` |
| Duplicate id | two records sharing one id | whole input rejected | `test_duplicate_ids_reject_the_whole_snapshot` |
| Repeated real event | same payload published twice | two rows with distinct sequence ids; no invented dedupe | `test_repeated_real_events_keep_distinct_sequence_ids` |
| Corrupted source view | source `snapshot()` patched to return a hostile record | zero rows, refusal token, recovery on next clean read | `test_corrupted_source_snapshot_yields_empty_rows` |
| Bus rejection | unlisted topic; integer `10 ** 13` | `SnapshotProducerError`, zero rows, next valid event still works | `test_publish_translates_host_bus_rejection_to_domain_error` |
| Invalid construction | capacity `0`/`13`/`True`/`"3"`; byte bound `0`/`65537`/`1.0`; fake source | constructor rejects | `test_invalid_constructor_arguments_are_rejected` |
| Lifecycle | `close()` twice, then `publish()` | disconnected, zero rows, publish refused | `test_close_fails_closed` |
| Source ownership | injected trusted source then producer `close()` | injected source remains connected | `test_injected_source_is_not_closed_by_the_producer` |
| Source integrity | AST import/allowlist and literal scan | no transport/execution import, no new topic string, no I/O call | `test_source_module_imports_no_transport_or_execution_module`, `test_no_new_topic_literal_and_no_io_in_source` |

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

All 39 tests are **SYNTHETIC** contract tests: they use real in-process
`HostEvent` deliveries for positive cases and synthetic record dictionaries
for validator controls; they never fabricate a `HostEvent`. The targeted
suite and any offscreen/compiled fixture are **SYNTHETIC** or **CI-SCOPED**
evidence only. Real live notification delivery, Linux Mint acceptance,
screen-reader behavior and owner visual approval are **NOT_RUN**. No maturity
level above the existing L3 UI / L2 contract is claimed here; the compiled
producer-to-adapter path is `AWAITING_WIRING`.
