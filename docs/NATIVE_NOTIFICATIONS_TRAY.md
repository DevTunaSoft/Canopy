# Native notification / tray contracts (M3, pure Python + scoped real-Plasma probe)

Owner directive SHA `79e30d79`, agent cap 8. This change is **draft-PR only**:
no merge, no approval, no release claim. It reuses the **existing upstream**
Plasma owner of `org.freedesktop.Notifications`; it never registers that name,
starts a notification daemon, installs a D-Bus service file or duplicates the
desktop notification facility.

## Owned paths

Only these paths are touched by this branch:

- `canopy_features/notifications/freedesktop_notifications.py` (new)
- `canopy_features/notifications/center_badge.py` (new)
- `canopy_features/notifications/tray_interaction.py` (new)
- `canopy_features/notifications/daemon_owner.py` (new)
- `docs/NATIVE_NOTIFICATIONS_TRAY.md` (this file, new)
- `scratch/native_notifications/**` (tests, real-Plasma probe logs, evidence)

No QML, C++, compiled input, approved artwork, workflow, `tests/` file,
host-event topic, payload field or protocol version is changed. The four new
adapters are pure in-process validators. The tests intentionally live under
the owned scratch path, so they are **not** part of Foundation CI's
`unittest discover -s tests`; this is recorded, not compensated by editing
another agent's files.

## Contracts

### `freedesktop_notifications.py` — delivery evidence from observations

Validates a host-supplied observation of the upstream `org.freedesktop.Notifications`
service. Exact identity: bus name `org.freedesktop.Notifications`, object path
`/org/freedesktop/Notifications`, interface `org.freedesktop.Notifications`.
Allowlisted members: `Notify.call`, `Notify.return`, `CloseNotification.call`,
`NotificationClosed.signal`, `GetCapabilities.call`,
`GetServerInformation.call`, `ActionInvoked.signal`.

| Bound | Value |
|---|---|
| Observation fields | exactly six: `bus_name`, `object_path`, `interface`, `member`, `owner`, `notification_id` |
| Owner | exact unique name `:1.N` (optional `:1.N.M`), <= 64 UTF-8 bytes |
| Notification id | exact `int` in `1..2**32-1` where required, `None` otherwise |
| Retained events | `1..32`, oldest evicted and counted |
| Refusals | `INVALID_NOTIFICATION_OBSERVATION`, `NOTIFICATION_OWNER_CHANGED` |

Availability is reported only when a complete round trip for one id (call,
matching return, close call, matching `NotificationClosed`) is observed under a
stable owner. A capability reply alone never claims delivery. An owner change
is sticky; recovery requires a fresh lifecycle. `evidence()` is a pure frozen
read; `close()` is explicit and idempotent.

### `center_badge.py` — center badge from trusted host events

`NotificationCenterBadge` accepts only an exact, connected
`HostSnapshotProducer`. Each `state()` re-composes the whole snapshot through
the existing `compose` contract; every row must be a trusted projected record
with the exact five keys, allowed topic and source. Counts are capped at 99.
A disconnected or rejected source reports `unavailable` with a zero badge.
No row is invented, no UI is opened, no pixel or screen-reader announcement is
produced.

### `tray_interaction.py` — tray interaction observation

Validates a host report of an upstream Plasma tray action. Exact facility
`org.kde.plasmashell`; allowlisted actions `OPEN_CENTER`, `DISMISS`,
`ACTIVATE`, `ACTION_INVOKED`; acknowledgement must be exact `True`; owner must
be a well-formed unique name. Wrong containers, extra/missing keys, hostile
mappings, unsafe code points, non-boolean acknowledgement and unknown actions
are refused with `INVALID_TRAY_OBSERVATION`. No click, popup, D-Bus call or
process is performed by this module.

### `daemon_owner.py` — single upstream owner proof

Validates a bounded host observation that must name `org.freedesktop.Notifications`,
an exact unique owner, an exact positive PID, an allowed upstream owner comm
(`plasmashell`), and **zero** foreign daemons, **zero** Canopy-owned
daemons/fixtures and **zero** activatable duplicate service files. Any doubt
is `INVALID_OWNER_OBSERVATION`; the owner string is never echoed into the state
surface. The probe budget is `1..8`. This module never requests a bus name and
never starts or checks out a daemon.

## Negative controls (`SYNTHETIC`)

All rows are deterministic finite tests in
`scratch/native_notifications/tests/test_m3_contracts.py`:

| Control | Synthetic input | Expected outcome |
|---|---|---|
| Foreign service identity | wrong bus name, object path or interface | fixed refusal; zero accepted events |
| Partial round trip | call/return without close signal | `unavailable` / `incomplete_roundtrip` |
| Owner change | second unique name after a full round trip | sticky `NOTIFICATION_OWNER_CHANGED` |
| Hostile mapping | finite mapping raising from `items`/`keys`/`__len__` with a marker | fixed refusal; marker absent from state |
| Wrong containers / bounds | `None`, `str`, `bytes`, `int`, `list`, `set`, bool ids, `0`, oversized ids | fixed refusal |
| Badge invention | disconnected producer; non-producer objects; bad bounds | unavailable zero badge / domain error |
| Tray action injection | unknown action, lowercase action, extra text, `False`/`1`/`"true"` | `INVALID_TRAY_OBSERVATION` |
| Duplicate daemon | foreign count 1, Canopy count 1, service file count 1, comm `dunst` | `unavailable`; `owner_verified=False` |
| Source integrity | AST import/literal scan | no transport, exec, Qt, poll, thread, filesystem or new host-event topic |

## Real-Plasma verification (scoped, exact commands)

Host: `MSYS_NT-10.0-26300`, `DBUS_SESSION_BUS_ADDRESS` unset, no
`dbus-send`/`gdbus`/`qdbus`. Guest: existing running VM `Canopy-Test-Plasma6`
(`VMState="running"`, SSH forward `127.0.0.1:2223`), Kubuntu Plasma session,
reached with the already-provisioned local SSH key artifact (no password was
typed, guessed or stored). Commands and raw output are in
`scratch/native_notifications/real_plasma/guest_harness_run2.log` and
`final_probe.log`.

| Gate | Verdict | Exact evidence |
|---|---|---|
| Single upstream notification daemon owner | **REAL_PLASMA_SCOPED PASS** | `gdbus call --session --dest org.freedesktop.DBus ... GetNameOwner org.freedesktop.Notifications` -> `(':1.22',)`; guest harness `10_owner_guard.sh` -> `OWNER_GUARD_PASS guarded_names=6 service_files=0`; owner `:1.22 pid=5422 comm=plasmashell`; `NO_FOREIGN_NOTIFICATION_DAEMON=YES`; `NO_CANOPY_NOTIFICATION_DAEMON=YES`; `ORG_FREEDESKTOP_NOTIFICATIONS_SERVICE_FILE_COUNT=0`; one compositor/shell. No duplicate daemon was started. |
| Fresh `org.freedesktop.Notifications` delivery round trip | **NOT_RUN** | `timeout 8 gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.freedesktop.Notifications.GetCapabilities` and `GetServerInformation`/`Notify` all returned `rc=124` (timeout) against the live owner at 2026-11-28T06:13:37Z and 06:24:14Z. `org.freedesktop.DBus.Peer.Ping` on the same object returned `()`, so the bus reply path works but the notification methods do not answer. No notification id was fabricated. |
| Fresh tray / notification-center interaction | **NOT_RUN** | Guest X clients time out: `timeout 6 xdotool getmouselocation` and `xdotool key Escape` -> `rc=124` even with `DISPLAY=:0` and the live `XAUTHORITY=/tmp/xauth_zdKrsq` read from the plasmashell process environment; `xdpyinfo` and `xset q` also produced no reply. No click, popup or unlock was forced. |
| Earlier live delivery + center interaction | `SCOPED_HISTORICAL_PASS` (not reused as a current claim) | Prior runtime artifact `native_notification_controls_runtime.json` records a PASS round trip and notification-center interaction at 2026-11-27T18:38Z with a different owner (`:1.100`); it does not prove the current guest state. |

The first owner-guard attempt self-matched its own SSH command line
(`canopy@...notification...` matched the forbidden Canopy pattern). That failed
attempt is retained in `guest_harness_run.log` as historical; the corrected
run invoked a guest-side runner whose command line carries no such token.

## Verification and evidence labels

Commands run at the exact branch head, from the worktree root with
`PYTHONPATH=<worktree>`:

```sh
python -m unittest discover -s scratch/native_notifications/tests -t . -v
python -m unittest tests.test_c100_notification_daemon_interop \
  tests.test_c100_notification_delivery_lifecycle \
  tests.test_c100_notification_host_snapshot \
  tests.test_notifications_host_event_source \
  tests.test_classic_notification_center \
  tests.test_c100_dock_notification_badges -v
```

- **SYNTHETIC:** 35 M3 contract tests (`OK` in 0.042s) plus 125 existing
  notification/dock/host-event tests (`OK` in 0.106s). Bounded frozen records,
  no daemon, transport, poll, timer, thread or file I/O in production modules.
- **REAL_PLASMA_SCOPED:** single-owner guard on the running Plasma guest; host
  and guest commands plus raw output are on disk with SHA-256 in `SHA256SUMS.txt`.
- **NOT_RUN:** fresh upstream delivery round trip and fresh tray/center
  interaction, with the exact timeouts recorded above. No Mint acceptance,
  compiled Qt bridge, CI-on-guest, screen-reader behaviour or owner visual
  approval is claimed.
- **screen-reader:** NOT_RUN — no UI, announcement or accessibility surface is
  touched or observed.
- No runtime RSS/CPU number is claimed. These are pure bounded validators;
  there is no long-lived process to profile.

`release_ready=false`; `visual_acceptance=AWAITING_OWNER`; draft PR only, no
merge and no self-approval.
