# Missing application handling (source contracts)

PE-063 adds one bounded, fail-closed availability contract for Classic's
catalog, dock and launcher source records. It is a pure Python contract: no
process launch, shell, filesystem access, polling, timer, network, Qt or visual
change. It does not constitute compiled Qt, Linux Mint or screen-reader
acceptance.

## Fixed decision record

`canopy_features/catalog/missing_app_availability.py` exposes:

- statuses `available` / `unavailable`;
- fixed reason codes `ok`, `not_in_catalog`, `entry_unreadable`,
  `tryexec_failed`, `probe_failed`, `refresh_exhausted`, `invalid_input`;
- immutable `AppAvailability` records with `launch_permitted` true only for an
  explicitly confirmed present application;
- `to_dict()` diagnostics containing counts, fixed tokens and a permission
  flag, never the application id or any source text;
- `MissingAppTracker` with bounded `observe()`, `refresh()` and `snapshot()`.

An unknown application is stably `unavailable / not_in_catalog`. A missing
entry, unreadable entry or failed `TryExec` probe each has its own fixed reason.
No state in this module starts a process or emits a launch intent.

## Bounded refresh

- One `refresh()` call makes at most `MAX_REFRESH_ATTEMPTS` (3) probe calls.
- Two consecutive positive probes are required before an unavailable state may
  become `available`; a single transient positive probe cannot permit a launch.
- Probe exceptions and malformed probe shapes become `probe_failed` rather than
  escaping to the host.
- A tracker allows at most `MAX_REFRESH_CYCLES` (8) refreshes per application;
  further calls probe nothing and keep `refresh_exhausted / unavailable`.
- The state cache is capped at `MAX_TRACKED_APPS` (256) and snapshots are
  immutable and ordered by application id.

## Launch-path enforcement

- `compose_dock_action_preview(..., availability=...)` denies a dock launch with
  `app_unavailable` when the supplied state (or a mapping keyed by dock label)
  is not launchable. The denial carries no target or action. Focus actions are
  unchanged.
- `compose_app_launch_preview(..., availability=...)` denies a launcher preview
  with `app_unavailable` when the supplied state is not launchable, and returns
  `invalid_input` for a wrong availability type. Existing callers that omit the
  argument keep their previous behavior.

## Verification

```sh
PYTHONPATH=. python3 -m unittest tests.test_pe063_missing_app_availability \
  tests.test_pe063_missing_app_dock_launcher -v
PYTHONPATH=. python3 -m unittest tests.test_c100_apps_app_launch_preview \
  tests.test_c100_apps_app_launch_preview_hostile_boundary \
  tests.test_c100_apps_launch_outcome_hostile_status_label \
  tests.test_c100_apps_launch_outcome_reconciler \
  tests.test_c100_dock_action_preview \
  tests.test_c100_dock_action_preview_duplicate_pinned_ids \
  tests.test_c100_dock_action_preview_reason_contradiction \
  tests.test_c100_launcher_shell_action_decision -v
```

These are offline deterministic unit tests (`SYNTHETIC`). Full suite, Qt build,
VM and screen-reader behavior are `NOT_RUN` for this change. No artwork, QML,
C++ or protected workflow file is modified.
