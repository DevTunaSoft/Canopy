# M4 native display response — multi-monitor and HiDPI

**Base / branch:** `ec910d7a7275296ecbc8b5e5c459d356205165d1`,
`product/native-display-response-20261127` (from
`integration/canopy-plasma6-20261127`).
**Directive:** SHA `79e30d79a580...`, M4 deployment and recovery, section 7;
evidence labels per section 11.
**Review state:** DRAFT PR only. No merge, no self-approval, no protected-branch
change.

## Scope and frozen presentation boundary

This change owns only:

- `canopy_features/dock/display_change_response.py`
- `canopy_features/dock/display_geometry_contract.py`
- `canopy_features/dock/display_scaling_contract.py`
- `docs/NATIVE_DISPLAY_RESPONSE.md` (this file)
- `scratch/native_display/**`

The approved dock geometry is `32/96/14/7` (directive section 5, PR #729) and
the approved wallpaper, icons, Tux branding, colours and typography are frozen.
No QML, C++, asset or layout file was edited here. At the exact base of this
branch the read-only Python mirrors in `display_geometry_contract.py` still
match the base `prototype/classic/Theme.qml` (`barHeight 32`, `dockSize 88`,
`dockPadding 12`, `dockSpacing 7`); that mirror was deliberately left byte-
identical. The `32/96/14/7` restoration belongs to PR #729 and is out of this
task's ownership, so this PR neither advances nor blocks it.

## Why a code change was needed

A host-side probe of the existing decision logic reproduced a bounded but
**false no-op** on monitor add/remove:

- `DisplayChangeResponse.handle_recovery_result` encoded only the surviving
  primary's connector, size and scale in its deduplication signature.
- Adding or removing a secondary monitor left that signature unchanged, so
  `handle()` returned `KIND_NO_OP / "unchanged"` and suppressed the plan.
- A primary disconnect with a surviving monitor was labelled `connect`, which
  misreported what happened even though the size stayed bounded.

RED evidence (base bytes): `scratch/native_display/probe_result_RED_base.json`
and `probe_stdout_RED_base.log` — scenarios `secondary_connect` and
`secondary_disconnect` fail their relayout assertions.

## Implemented bounded response

`DisplayChangeResponse` now accepts an optional, bounded `changes` signature
on `DisplayEvent` and includes it in deduplication. The recovery adapter fills
it from the frozen `RecoveryResult` as a sorted tuple of
`(change.kind, change.connector)` pairs, capped at 16 entries of at most 80
characters. Hostile `changes` values fail closed as `invalid_event` holds;
ordinary direct events keep `changes=None` and keep their prior behaviour.

A `disconnect` event that carries a surviving primary's size now yields a
bounded `relayout` with reason `disconnect` instead of a desktop-wide
`suspend`; a disconnect with no size still suspends with `no_display`. All
plans remain clamped to the frozen Classic root, are checked against the
frozen dock geometry contract and stay inside the existing 64-plan history and
16-subscriber bounds. No timer, thread, polling loop, Qt import, window resize,
binding change or asset write was added.

Decision table (M4 relevant rows):

| Situation | Kind | Size | Reason |
| --- | --- | --- | --- |
| Secondary monitor connected; primary unchanged | `relayout` | clamped primary logical size | `connect` |
| Secondary monitor disconnected; primary survives | `relayout` | clamped primary logical size | `disconnect` |
| Primary disconnected; another monitor reanchored | `relayout` | clamped surviving primary logical size | `disconnect` |
| Last monitor disconnected | `suspend` | last safe size | `no_display` |
| HiDPI 1920x1080 physical at 150% | `relayout` | `1200x720` logical | `logical_dpi_changed` |
| HiDPI 2560x1440 physical at 200% | `relayout` | `1200x720` logical | `logical_dpi_changed` |
| DPI signal with unchanged logical size | `no_op` | last safe size | `logical_size_unchanged` |
| Malformed event / scale / changes | `hold` | last safe size | `invalid_event` |
| Consecutive identical event signature | `no_op` | computed size | `unchanged` |

Physical monitor pixels are never substituted for logical layout pixels (the
150% trap); `display_geometry_contract` still reports physical extents
separately and validates dock bounds in logical space only.

## Verification performed

| Check | Command | Result |
| --- | --- | --- |
| Targeted display tests at base (before fix) | `PYTHONPATH=<wt> python -m unittest discover -s tests -p 'test_*display*' -v` | `Ran 79 tests ... OK` — `targeted_tests_base.log` |
| Targeted display tests after fix | same command | `Ran 79 tests ... OK` — `targeted_tests_fixed.log` |
| M4 scenario probe at base | `python scratch/native_display/probe_display_response.py` | FAIL: 2/9 scenarios; RED evidence above |
| M4 scenario probe after fix | same command | PASS: 11/11 scenarios — `probe_result.json`, `probe_stdout.log` |
| Guest readiness probe on this host | `python scratch/native_display/guest_probe.py` | `NOT_RUN`, `HOST_ADAPTER_ABSENT` — `guest_probe_host_check.json` |
| Full suite | bounded `python -m unittest discover -s tests` | see `full_suite_final.log` / `full_suite_final.rc`; an earlier 480 s bounded run timed out (`full_suite.log`) and is recorded as INCOMPLETE, never as a pass |

All verification above is `SYNTHETIC` decision-logic testing on the Windows
host. It does not prove compiled Qt or Plasma behaviour.

## Native runtime blocker

`NATIVE_RUNTIME = NOT RUN`. A Plasma 6 VM is registered and running, but no
compiled host adapter at this exact base consumes the response entry points,
guest additions are not reporting, NAT has no forwarding rule, and no
authorized guest login was available. The exact commands, outputs and next
action are in `scratch/native_display/plasma_runtime_blocker.md`. The
read-only in-guest probe for the follow-up is
`scratch/native_display/guest_probe.py`. No screenshot, compositor behaviour
or real monitor/scale-change result is claimed here.

## Resource and evidence note

- `SYNTHETIC`: targeted Python test counts/durations and the 11-scenario probe
  on the Windows host; no PSS, CPU or GPU number was measured.
- `NOT_RUN`: full-suite terminal verdict if the bounded run does not finish,
  compiled Qt frames, real Plasma session, real monitor add/remove, real
  HiDPI scale changes, sustained 24-hour behaviour and screen-reader
  announcements.
- The change adds one optional tuple field with at most 16 bounded entries per
  event and no cache, service, polling loop, animation or asset. It does not
  trade stability, security, accessibility or approved visuals for a gain.
- Screen-reader behaviour: `NOT_RUN` (no announcement path was added or
  exercised).

## Integration boundary

This PR is a draft review artefact. Independent review, applicable CI, visual
gate and any merge decision remain separate and are not performed by this
task. No PR was merged or approved by this worker.
