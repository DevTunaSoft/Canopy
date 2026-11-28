# M4 native display response — multi-monitor and HiDPI

**Status:** code-complete for independent review only. `DRAFT` PR, no merge,
no self-approval, no protected-branch change, no visual edit.

**Base:** `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(`integration/canopy-plasma6-20261127` tip at branch point).
**Branch:** `product/native-multimonitor-20261128`.
**Directive:** Rev3 master directive, M4 deployment and recovery
(multi-monitor/HiDPI) and the frozen geometry record in the PR #729 section.

## Owned paths

Only these paths are changed by this workstream:

- `canopy_features/dock/display_change_response.py` (additive native push seam)
- `canopy_features/dock/geometry.py` (new read-only geometry mirror)
- `docs/NATIVE_DISPLAY_RESPONSE.md` (this file)
- `scratch/native_multimonitor/**` (headless fixtures and evidence)
- `tools/display_response/**` (fixture runner and bounded checks)

No QML, C++, artwork, wallpaper, icon, colour, typography or geometry source
file is edited. The repository's `tests/` directory is not owned here; the
new tool-side checks live beside the tool and are invoked explicitly.

## Contract consumed from KWin / KScreen

The shell does not discover displays itself. A trusted host that already owns
the KWin/KScreen signal calls one push method with one bounded payload:

```python
plan = response.handle_native_change(payload)
```

No timer, thread, poll loop, socket, D-Bus connection, process, Qt window or
second subscription service is created. The only new state in the response is
a bounded last-snapshot footprint (at most 16 connectors) used for duplicate
suppression. No host-event topic is added: the documented `HostEvents` topic
allowlist stays unchanged.

Three source tokens are accepted; anything else is held as `invalid_event`.

| `source` | Producer signal | Required fields | Meaning of `width`/`height` |
| --- | --- | --- | --- |
| `kscreen.configChanged` | trusted KScreen configuration change | `outputs`: at most 16 objects with `connector`, `width`, `height`, optional `scale` (default 1.0) and optional `primary` (default false) | physical monitor pixels; converted once to logical pixels |
| `kwin.screensChanged` | trusted KWin screen add/remove | `screens`: at most 16 connector strings, `primary`, `width`, `height`, optional `scale` | logical pixels of the primary screen |
| `qt.logicalDpiChanged` | trusted Qt/QScreen logical-DPI signal under KWin | `connector`, `width`, `height`, `scale` | physical monitor pixels plus device scale |

Validation is strict and fails closed: exact type checks (no `bool` as an
integer), connector syntax `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, dimensions
`1..7680` / `1..4320`, finite scale in `(0, 4]`, unique connectors, exactly
one primary for a non-empty KScreen topology, no unknown payload fields and
no size on an empty topology. JSON fixtures additionally reject duplicate
object keys before dispatch. A malformed push returns the existing
`KIND_HOLD / invalid_event` plan and leaves the remembered topology untouched.

Attach/detach is derived from the connector set difference between two pushes,
so a secondary monitor add/remove is not silently deduplicated when the
surviving primary's connector and size are unchanged. The response keeps the
existing 64-plan history, 16-subscriber cap and 1200x750 / 720x480 frozen
root bounds. A detach with a surviving primary yields one bounded relayout;
only the last monitor disconnected yields `suspend / no_display`.

## Decision table (headless, SYNTHETIC)

| Situation | Kind | Size | Reason |
| --- | --- | --- | --- |
| First bounded KScreen/KWin snapshot | `relayout` | clamped logical primary | `resolution_changed` |
| Secondary attached, primary unchanged | `relayout` | clamped logical primary | `connect` |
| Secondary detached, primary survives | `relayout` | clamped logical primary | `disconnect` |
| Primary detached, survivor reanchors | `relayout` | clamped surviving primary | `disconnect` |
| Last monitor detached | `suspend` | last safe size | `no_display` |
| DPI 1920x1080 physical at 150% | `relayout` | `1200x720` logical | `logical_dpi_changed` |
| DPI 2560x1440 physical at 200% | `relayout` | `1200x720` logical | `logical_dpi_changed` |
| Scale change with unchanged logical size | `no_op` | last safe size | `logical_size_unchanged` |
| Identical repeated snapshot | `no_op` | computed size | `unchanged` |
| Below-minimum logical size | `hold` | last safe size | `below_minimum` |
| Hostile payload / scale / connector / topology | `hold` | last safe size | `invalid_event` |

Physical monitor pixels are never substituted for logical layout pixels (the
150% trap). Dock bounds remain validated in logical space only.

## Frozen geometry boundary

The approved dock geometry tuple is **`32/96/14/7`** (bar height, dock size,
dock padding, dock spacing). `canopy_features/dock/geometry.py` is a read-only
mirror of that tuple with a stable fingerprint (`sha256("32/96/14/7")`). It
parses only QML text supplied by a caller and reports whether that text
matches; it never writes, regenerates or repairs presentation source.

At this exact base, `prototype/classic/Theme.qml` still carries the older
mirror `32/88/12/7`. The fixture runner reports that divergence as
`matches_approved=false` and leaves the file byte-identical. Restoration of
the approved tuple belongs to the owner-gated PR #729, not to an M4 decision
module. No visual acceptance is claimed here.

## Verification performed

| Check | Command | Result |
| --- | --- | --- |
| Headless KWin/KScreen fixtures | `python tools/display_response/run_fixtures.py` | `PASS_SYNTHETIC`, 15 scenarios / 27 steps, 27/27 (`scratch/native_multimonitor/evidence.json`) |
| Tool-side bounded checks | `PYTHONPATH=<wt> python -m unittest discover -s tools/display_response -p 'test_*.py'` | `Ran 6 tests ... OK` (`tool_tests_head.log`) |
| Existing display suites at pinned base | `PYTHONPATH=<base> python -m unittest discover -s tests -p 'test_*display*'` | `Ran 79 tests ... OK` (`targeted_tests_base.log`) |
| Existing display suites at head | same command with worktree `PYTHONPATH` | `Ran 79 tests ... OK` (`targeted_tests_head.log`) |
| No polling / duplicate service tokens | fixture runner static check | `no_polling_or_duplicate_service=true`, no banned token found |

All numbers above are `SYNTHETIC` pure-Python decision-logic checks on the
Windows host. They do not prove compiled Qt, Plasma or desktop behaviour.

`NOT_RUN`: full-suite terminal verdict, compiled Qt host bridge, real Plasma
session, real monitor attach/detach, real scale changes, sustained event
bursts, 24-hour endurance, PSS/CPU measurement and screen-reader announcements.

## Native runtime blocker

`NATIVE_RUNTIME = BLOCKED / NOT_RUN`. The compiled host bridge on the
unmerged M2/M3 branch (`product/native-host-wiring-20261128`, PR #754) does
not consume this new seam at the exact base of this branch; it targets a
different Python contract. No authorized guest login, guest-additions channel
or compiled adapter exists here that could deliver a genuine KScreen/KWin
signal. No screenshot, compositor frame, monitor or HiDPI result is claimed.
The next action is owner-gated host wiring plus a real Plasma guest run.

## Resource / evidence note

- `SYNTHETIC`: fixture and unittest counts/durations; no PSS, CPU or GPU
  measurement was made.
- `NOT_RUN`: real-runtime items listed above; `screen-reader` behaviour is
  `NOT_RUN` because no announcement path was added or exercised.
- The change adds one bounded push method, one tuple of at most 16 screen
  records and one read-only geometry module. It adds no cache, timer, service,
  rendering loop or asset and does not trade stability, security,
  accessibility or the approved visuals for a minor gain.

## Overlap boundary and integrator choice

PR #746 (`product/native-display-response-20261127`, OPEN, non-draft (live)) touches two
of the same owned paths from the same base:
`canopy_features/dock/display_change_response.py` (modification) and
`docs/NATIVE_DISPLAY_RESPONSE.md` (added in that PR). This branch is an
additive, independent candidate, not a rebase or a stacked PR; no merge,
approval or scope takeover is performed here.

The integrator choice is explicitly deferred: after exact-SHA review the
integrator decides whether to (a) take this branch's bounded push seam,
(b) take PR #746's implementation, or (c) combine both by resolving the two
shared paths deliberately. This workstream does not merge, approve, re-pin,
close or otherwise act on PR #746. The reviewed evidence head of this branch
is pinned in `scratch/native_multimonitor/head.txt`; the final pushed head is
cited in the PR body. The runtime verdict remains
`NATIVE_RUNTIME = BLOCKED / NOT_RUN` under either choice until a real Plasma
guest exercises the selected compiled adapter.

## Bounded evidence remediation (PR #758 gaps)

The sealed evidence pins the exact reviewed head in
`scratch/native_multimonitor/head.txt`, with base
`ec910d7a7275296ecbc8b5e5c459d356205165d1`. `git_diff_names.txt` now lists
the 15 live paths of `git diff --name-only <base>..<reviewed head>`. Re-run at
that head: 15 scenarios / 27 steps with 27/27 passed (`PASS_SYNTHETIC`),
6 tool-side unittest checks `OK`, and the existing 79 display tests `OK` at
both the pinned base and the head. No runtime verdict was upgraded.

## Intentional CRLF in byte-pinned evidence

`scratch/native_multimonitor/evidence.json` and the three
`targeted_tests_base.log`, `targeted_tests_head.log` and `tool_tests_head.log`
files use CRLF. The fixture runner emits text with Python `Path.write_text`
on this Windows host, which translates its LF output to CRLF; a rerun of the
runner reproduced `evidence.json` byte-for-byte. Those four files are
byte-pinned in `SHA256SUMS.txt`, so normalizing their line endings would
change the pinned bytes and invalidate the digests. The CRLF is therefore
intentional and preserved: `git diff --check` reports trailing whitespace on
those lines as a CRLF artifact, not as added spaces. Pinned digests:

- `evidence.json` `957041f322821a9b227e01f741b0a6663146f5e91205e2dba0018ad90cbd6d34`
- `targeted_tests_base.log` `07c30d0cf3e95cfce83878f33f9702fc26c0ce826afd58478d2117441484098b`
- `targeted_tests_head.log` `28bc168217556b9f41c569c34aacb93c43fac039d4ada5ef9dd54cfba2f6be58`
- `tool_tests_head.log` `dd74a93ffde369c932266349f924f83d85a76d8ebe74d133d969bc1b458cb471`
