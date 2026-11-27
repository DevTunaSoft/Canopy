# Classic panel/session lifecycle notification contract (pure Python)

This document describes a **nonvisual, pure-Python** lifecycle contract for the
Classic notification panel. It decides when trusted, already-projected notice
rows may be surfaced; it is not a compiled Qt bridge, a notification daemon, a
live desktop notification source, a real session change or a screen-reader
announcement.

## Scope and ownership

Exactly three new repository paths are owned by PE-110:

- `canopy_features/notifications/panel_lifecycle.py`
- `docs/CLASSIC_PANEL_LIFECYCLE_CONTRACT.md`
- `tests/test_pe110_panel_lifecycle.py`

No existing module, host-event contract, QML/C++ file, compiled input, approved
artwork, workflow or protected file is edited. In particular this change does
not touch the owned paths of PR693 (`delivery_lifecycle.py`), PR700
(`daemon_interop.py`), PR697, PR699, PR701, PR703, PR705, PR707 or PR708.

The module composes the existing trusted-source boundary
(`canopy_features/notifications/host_event_source.TrustedHostEventSource`) and
the existing record validator (`host_snapshot_producer.compose`). It reuses
protocol-v2 `HostEvent` and its four topics from `canopy_core.host_events`, the
`{id, title, body, source, topic}` record shape and the session status tokens
from `quick_controls_state`. It adds **no** topic, protocol version, payload
field or status token.

## What the contract guarantees

`PanelSessionLifecycle` is a host-owned, single-thread view over one trusted
source. Panel visibility (`closed`/`open`/`obscured`) and host availability are
explicit trusted signals, **not** new host events: QML and community Shell
Packs cannot construct an event or drive the boundary.

| Contract | Behaviour |
|---|---|
| Fail-closed default | Panel `closed`, session `unknown`, zero rows; disclosure `Unavailable — no session observation`. |
| Cross-field surface rule | Rows are exposed only when panel is `open`, session is `active`, the boundary is trustworthy, the source is connected and no re-observation is owed. Any paired contradiction (open + unobserved, active + closed) yields zero rows. `surfacing` is derived from these durable fields, never from an overridable flag. |
| Obscure on privileged session | A `locked`/`suspended` observation sets the panel to `obscured`, hides all rows and requires explicit `acknowledge_reobservation()` plus `open_panel()` before rows return. |
| Boundary loss | Invalid observation, forged `HostEvent` subclass, unprojectable source row, or `mark_host_unavailable()` clears the session view, hides rows and refuses intake until `restore_host()` and a fresh observation/acknowledgement. A late event cannot resurrect the old view: sequence numbers stay monotonic and stale events are counted. |
| Bounded surface | Notice capacity is the source's own bound (12, lower on request); history is capped at 12 and a publish batch consumes at most 32 items. `publish_many` uses `islice`, so a hostile iterator cannot pin the host callback. |
| Fixed refusals | Hostile caller types and rejected payloads raise `PanelLifecycleError` with fixed text. No rejected value, exception message or caller string reaches a disclosure or snapshot. |
| Ownership | A lifecycle that created its source closes it; an injected trusted source stays host-owned and connected after `close()`. |

`snapshot()` returns an immutable deterministic projection (fixed key order,
read-only nested records/counters/frozen history); `to_dict()` returns a fresh
JSON-friendly copy. Rows are newest first and keep the source's existing ids.

## Negative-control table (`SYNTHETIC`)

Every case below is a deterministic synthetic probe in
`tests/test_pe110_panel_lifecycle.py` using real in-process `HostEvent`
deliveries or clearly marked forged objects; no case uses a real session.

| Control | Synthetic input | Expected outcome |
|---|---|---|
| Protocol drift | topic set, `SESSION_TOPIC`, status tokens, AST import/literal scan | no new topic/version/field, no transport or execution import |
| No observation | default view | closed/unknown, zero rows, fixed disclosure |
| Cross-field contradiction | open panel + catalog-only events | zero rows (`no-session-observation`) |
| Active + closed panel | active session event before `open_panel()` | zero rows, then rows after open |
| Lock/suspend | `locked`/`suspended` session event | panel `obscured`, zero rows, reopen refused |
| Re-observation | return to `active` after suspend | rows stay hidden until explicit acknowledgement |
| Invalid observation | `{"state": "SECRET_MARKER"}` | domain error, boundary lost, no secret in text/disclosure |
| Host unavailable | `mark_host_unavailable()` | boundary lost, zero rows |
| Stale/replay | lower/equal sequence `HostEvent` | counted stale, session unchanged |
| Forgery | `HostEvent` subclass | domain error, boundary lost, zero rows |
| Wrong types | malformed bounds, source, payload, batch container/item | domain error, no raw built-in leak |
| Bounded batch | 51 pairs with `max_batch=3` | exactly 3 consumed/accepted |
| Overflow | five real events into capacity 3 | 3 newest rows, 3 counted drops |
| Source loss | close injected source | `source-lost`, zero rows |
| Close | double close, then publish/open | `lifecycle-closed`, zero rows, domain error |
| Immutability | mutate returned view/record | `TypeError`; internal state unchanged |

## Non-behaviour (deliberately absent)

No D-Bus, socket, daemon, process spawn, timer, polling, thread, filesystem or
network access; no Qt import, compositor call, session lock/logout/shutdown,
permission, focus, sound, screen-reader announcement or visual change. No real
desktop notification, Mint acceptance or owner visual approval is implied. The
compiled producer-to-panel bridge stays `AWAITING_WIRING` and is a separate
workstream. No merge into `main` is requested.

## Verification and evidence labels

Targeted run from the worktree root (with `PYTHONPATH` pinned to that root):

```sh
python -m unittest tests.test_pe110_panel_lifecycle -v
```

All 18 cases are **SYNTHETIC** contract tests. Real live panel behaviour,
screen-reader announcements, Linux Mint acceptance and owner visual approval
are **NOT_RUN**. Resource-impact evidence is likewise **SYNTHETIC**: bounded
deques/dataclasses only, no allocation profile or runtime PSS measurement was
run (`NOT_RUN`); the change removes no work and trades no stability, security,
accessibility or approved visual quality for a minor gain. The module touches
no announcement or accessibility surface, so screen-reader behaviour is
unchanged and unverified here.

Evidence: `scratch/master_directive_20261126/evidence/panel_lifecycle_contracts/`
(Hermes cache scratch root on this host), with SHA-256 sidecars.
