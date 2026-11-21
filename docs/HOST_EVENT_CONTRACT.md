# Canopy Shell Host event contract — in-process protocol v1

`canopy_core.host_events.HostEvents` is a **small, bounded, host-owned event
primitive** for future Classic, Modern and third-party presentation adapters
under the same trusted host. It does not integrate with Qt Quick, observe
real windows, install anything, load untrusted Shell Packs, enforce sandbox
permissions, authenticate external events or imply working live desktop
switching. It is not a daemon or communication bus between processes.

## Scope and data shape

Protocol version **1** accepts only these event topics:
`app.catalog.changed`, `window.state.changed`,
`session.state.changed`. Exact topic spelling is required.

An immutable `HostEvent(version, topic, sequence, fields)` is emitted with
monotonic per-bus sequence numbers and a sorted tuple of scalar fields;
`event.payload` returns a new read-only mapping. Payloads contain at most
eight ASCII lowercase snake-case keys of up to 48 characters. Common
sensitive or prototype-pollution names (`__proto__`, `constructor`,
`prototype`, `token`, `secret`, `password`, etc.) are forbidden.
Values are bounded UTF-8 strings (up to 512 bytes), booleans, integers,
finite small floats, or `None`. Nested objects, lists and executable
data are rejected before any callback runs.

## Trust and lifecycle

Only explicitly trusted **host code** constructs the bus and supplies an
identity allowlist of supported callback functions. Each callback can be
subscribed once per topic, up to 64 active subscriptions (configurably less).
The bus cannot import/execute callback paths from a manifest or use a
Python name supplied by a community theme. This is identity approval,
**not** an isolation sandbox for already trusted host code.

Callbacks run synchronously, in subscription order, on the owning thread.
Nested event dispatch, subscribe/unsubscribe and close are prohibited while
a callback is running. Callback exceptions are counted, without leaking
their message or preventing other approved callbacks from running.
Unsubscribe removes a token deterministically. `close()` clears every
subscription and callback reference; later emissions and registrations are
rejected. There is no worker thread, timer, event poll, process, filesystem
read, network connection or telemetry.

Example **inert host-side usage only**:

```python
from canopy_core.host_events import HostEvents

def on_catalog_change(event):
    assert event.payload["item_count"] >= 0

bus = HostEvents({"app.catalog.changed": [on_catalog_change]})
token = bus.subscribe("app.catalog.changed", on_catalog_change)
result = bus.emit("app.catalog.changed", {"item_count": 8})
assert (result.delivered, result.callback_failures) == (1, 0)
bus.unsubscribe(token)
bus.close()
```

This demonstration does not update the actual desktop or install apps.
Only a future reviewed Qt/session adapter could generate genuine
window/session events; it must prove lifecycle cleanup, trust boundaries,
CPU wakeups and rollback, and cannot turn metadata declarations into
execution authorization.

`tests/test_host_events.py` covers incompatible versions, duplicate and
nonhost callbacks, unsafe payloads, bounded subscription limits, immutable
data, deterministic order, callback failures, reentrancy, cleanup and cross-
thread denial. Tests use inert functions and should not be represented as
Mint guest or compositor acceptance.
