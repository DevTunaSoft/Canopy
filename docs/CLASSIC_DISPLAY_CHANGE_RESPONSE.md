# Classic display-change response (PE-025)

## Scope

This document records the offline decision contract for display resolution,
monitor connect/disconnect and primary-screen changes in Canopy Classic. It
keeps the approved Classic layout frozen: no QML, C++, asset, colour, icon or
dock-geometry file is changed by this work.

The implementation is
`canopy_features/dock/display_change_response.py`, with targeted regression
tests in `tests/test_pe025_display_change_response.py`.

## Event-driven contract

Nothing in this module polls a display, starts a thread, registers a timer or
imports Qt. A trusted host owns all observation and calls one of two entry
points **only when a real screen signal arrives**:

- `DisplayChangeResponse.handle(event)` for one validated `DisplayEvent`;
- `DisplayChangeResponse.handle_recovery_result(result)` to adapt a frozen
  `RecoveryResult` produced by
  `canopy_features/reliability/screen_topology_change.py`.

`subscribe(callback)` registers a bounded push callback (at most 16). Every
non-duplicate decision is delivered synchronously to all current subscribers;
`unsubscribe(token)` revokes one. A callback that raises is counted in
`failed_notifications` and cannot crash dispatch.

## Decision table

Each call returns one immutable `RelayoutPlan(sequence, kind, size, reason)`:

| Event / condition | Kind | Size | Reason |
| --- | --- | --- | --- |
| Valid resolution/connect/primary change that fits | `relayout` | `min(1200,width) x min(750,height)` | event kind |
| Screen below Classic minimum `720x480` | `hold` | last safe size | `below_minimum` |
| No monitor / all displays disconnected | `suspend` | last safe size | `no_display` |
| Geometry rejected by the frozen dock contract | `hold` | last safe size | `unsafe_geometry` |
| Hostile or malformed event payload | `hold` | last safe size | `invalid_event` |
| Consecutive identical event signature | `no_op` | computed plan size | `unchanged` |

Hostile display data never raises: wrong types, booleans, NaN/infinite scales,
negative or oversized geometry and unknown producers all fall back to a safe
hold. API misuse (non-callable subscriber, invalid unsubscribe token, too many
subscribers) raises the module's `DisplayChangeError` instead.

Bounds: monitor geometry uses the existing `MAX_WIDTH`/`MAX_HEIGHT` limits,
scale is finite in `(0, 4]`, history is a deque of at most 64 plans, and
connector names follow the existing topology regex.

## Frozen presentation boundary

`ROOT_WIDTH=1200`, `ROOT_HEIGHT=750`, `MIN_WIDTH=720` and `MIN_HEIGHT=480` are
read-only mirrors of `prototype/classic/Main.qml`; the regression test asserts
the constants still appear in that source. Physical sizes are deliberately
not mixed with logical sizes: the existing
`canopy_features/dock/display_geometry_contract.py` validates the dock in
logical pixels and reports physical extents separately (the 150% trap).

A plan is a decision, not a rendered frame. The module does not resize a
window, redraw the dock, change a QML binding or approve a visual state.

## Wiring status

`NOT_RUN`: compiled Qt build, QScreen signal connection, Linux Mint guest,
real monitor changes and screenshot capture were not performed under this
task's targeted-tests-only constraint. The intended host seam is to connect
`QGuiApplication::screenAdded`, `screenRemoved`, `primaryScreenChanged` and
`QScreen::geometryChanged` to a topology producer that calls
`handle_recovery_result`, then apply only `relayout` plans to the existing
window geometry. That compiled wiring remains a separate, reviewable change.

## Resource and evidence labels

Measured (`SYNTHETIC`): targeted Python test counts, durations and artifact
SHA-256 values on the Windows 11 host. Deliberately not measured (`NOT_RUN`):
full-suite counts, shell-owned PSS, CPU, GPU, wakeups, compiled Qt frames,
real Mint session behavior and screen-reader behavior. The change adds one
bounded deque and at most 16 subscriber references; there is no new service,
polling loop, asset, animation or accessibility announcement, so no stability,
security, accessibility or approved-visual tradeoff is made.
