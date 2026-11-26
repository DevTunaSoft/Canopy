# Application crash contracts at the source boundary

`canopy_features/reliability/app_crash_contracts.py` is a pure, in-process
contract over the **existing** `canopy_core.host_events` protocol v2 bus. It
adds no topic, no protocol version, no callback registration from data, no
thread, timer, poll, socket, filesystem access, telemetry, process launch,
signal or kill. It does not touch Qt, QML, artwork, window geometry or any
approved visual asset.

## Existing host events used

Only two of the four v2 topics are consumed:

| Topic | Fields used (all already legal v2 payload fields) | Meaning here |
|---|---|---|
| `window.state.changed` | `state`, `app_id`, `pid`, `exit_code` | one caller-declared application exit signal |
| `session.state.changed` | `state`, `phase`, `app_id` | one explicit recovery grant after cleanup |

There is no fifth topic and no protocol change. `docs/HOST_EVENT_CONTRACT.md`
still governs the envelope: bounded scalar snake-case fields, trusted host
callbacks, synchronous single-thread dispatch and fail-closed payloads. Only
trusted host code may call `TrustedCrashEventSource.emit`.

## Lifecycle

1. **Detect.** `state="crashed"` with a valid bounded `app_id`, `pid` and
   `exit_code`, or `state="exited"` with a nonzero `exit_code`, yields one
   crash record. Clean exits, unknown states, wrong types (including `bool`
   as a PID), control characters in `app_id`, out-of-range codes, stale
   sequences and duplicate application names create no crash claim.
2. **Isolate.** A detected crash marks only that `app_id` isolated. Other
   applications are unaffected. The registry is capped at
   `MAX_TRACKED_APPS = 32`; when full, new crashes are refused rather than
   evicting a real isolation record. Application ids are bounded ASCII
   (`[A-Za-z0-9][A-Za-z0-9._+-]{0,63}`).
3. **Bounded cleanup.** `cleanup(app_id, resources)` accepts an ordered tuple
   of at most eight declared resource names and releases at most
   `MAX_CLEANUP_STEPS = 4` per call. Repeated calls are idempotent: a released
   name is never released twice. Unknown names or wrong container types fail
   closed before any state changes; cleanup is denied for a non-isolated
   application.
4. **Recovery.** A `session.state.changed` event with `state="active"`,
   `phase="recovery_granted"` and the same valid `app_id` grants recovery
   **only** after all declared resources are done. `acknowledge(app_id)` then
   clears isolation and increments the recovery count, which is capped at
   `MAX_RECOVERIES = 64`; further grants are refused rather than growing state.
5. **Stable feedback.** `feedback(app_id)` returns a frozen code/message pair
   from a fixed table. It never echoes the application id, PID, exit code,
   raw event text or exception message, and it stays available after close.

`close()` is idempotent: it unsubscribes, closes the bus and clears all
records; later emissions and cleanup calls fail closed.

## Feedback table

| Code | Message | When |
|---|---|---|
| `READY` | `Canopy is ready.` | no isolation for the named application |
| `APP_ISOLATED` | `An application stopped unexpectedly. Canopy kept the desktop available.` | crash detected, recovery not granted |
| `APP_RECOVERABLE` | `The application can be restarted safely.` | cleanup done and recovery granted |
| `STATE_UNAVAILABLE` | `Crash state is unavailable. Use the safe exit control.` | closed controller or hostile input |

These are provider strings only. No compiled Qt/host adapter consumes them in
this change, so screen-reader announcement behavior is `NOT_RUN`.

## Evidence and non-claims

`tests/test_reliability_app_crash_contracts.py` drives real `HostEvent`
objects through the real bus. One bounded test starts a synthetic Python child
that exits by itself with code 7 under a five-second timeout; no signal, kill
or host process is involved. That observation is `SYNTHETIC`, not a desktop
runtime measurement. Real Mint/Qt crash behavior, actual process supervision,
PSS/CPU and screen-reader output are `NOT_RUN`; acceptance stays
`NOT_ESTABLISHED`. A passing source test is not proof that a hard process
crash is caught on a live desktop.
