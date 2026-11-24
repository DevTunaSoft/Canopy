# Integrator lock and recovery contract

## Incident

On 2026-11-24 18:41 UTC the overlap monitor reported:

```
CANOPY MONITOR ALERT:
 - integrator lock present but PID is dead: 28432
```

The integrator had last written a healthy heartbeat at 18:40:34 UTC, then its
process ended without executing the `finally: LOCK.unlink()` path. The old lock
format was a plain PID file, so the monitor could only check liveness; it could
not distinguish a stale PID from a reused PID, validate ownership before
removal, or restart the daemon safely. A separate defect in the suite parser
(`FAILED (errors=5, skipped=43)` was unparseable) had already been fixed, but
abnormal termination remained possible (gateway/session teardown, forced kill,
OS shutdown).

## Design

`tools/qa/integrator_lock.py` replaces the plain PID file with an atomic JSON
lock:

- `pid`, `start` (OS process start time), `token` (UUID), `ts` heartbeat,
  `host`, `owner`.
- `acquire()` uses `O_CREAT | O_EXCL`, so concurrent contenders cannot both win.
- `process_alive()` checks liveness **and** the recorded start time, preventing
  PID reuse from being mistaken for the original owner.
- `release()` and `touch()` verify the UUID token; a stale owner cannot delete
  or overwrite a newer lock.
- `lock_state()` classifies `absent`, `live`, or `stale` with an explicit reason.
  A live process with a stale heartbeat is reported as
  `heartbeat_stale_but_process_alive`; it is **never** killed or unlocked.
- Legacy integer locks are classified live while their PID is alive (safe migration) and stale only after that PID dies; malformed locks are stale and recoverable.

`tools/qa/integrator_recovery.py` adds bounded supervision:

- Recovers only locks whose owner is dead, PID-reused, dead legacy, or malformed.
- Launches the replacement detached from the calling shell/session, so gateway
  restarts and terminal teardown do not kill it.
- Records attempts in `<lock>.recovery.json`; at most two attempts per 15-minute
  window. Further failures alert instead of retrying in a tight loop.
- No polling loop, no extra GitHub API calls, and no process termination.

The overlap monitor keeps its original overlap and heartbeat checks. It uses
the shared lock classifier and recovery helper, so it alerts on genuine
anomalies and silently recovers only the safe stale-lock case.

## Operations

- Lock: `~/AppData/Local/hermes/cache/scratch/canopy_integrator.lock`
- Heartbeat: `.../canopy_integrator_heartbeat.jsonl`
- Recovery ledger: `.../canopy_integrator.lock.recovery.json`
- Daemon log: `.../canopy_integrator_restart.log`
- Monitor cron: `63e9d4015747` (`canopy_overlap_monitor.py`, every 3 minutes)

Manual check (does not alter state):

```shell
python -c "from tools.qa.integrator_lock import lock_state; print(lock_state(r'C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy_integrator.lock'))"
```

## Evidence note

All tests are synthetic/local Windows Python 3.14.9 unit tests using temporary
lock files and short-lived detached child processes. No Qt, Linux Mint, visual
asset, or release claim is made here.
