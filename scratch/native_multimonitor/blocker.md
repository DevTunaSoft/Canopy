# Native runtime blocker — M4 multi-monitor / HiDPI

**Verdict:** `BLOCKED` / `NOT_RUN`. No real desktop, compositor, monitor or
HiDPI result is claimed by this workstream.

## Why the real runtime was not exercised

1. The base is `ec910d7a7275296ecbc8b5e5c459d356205165d1`
   (`integration/canopy-plasma6-20261127`). A source search at that exact
   commit found no definition and no consumer of `handle_native_change`:

   ```text
   git grep -n 'handle_native_change' ec910d7a -- '*.py' '*.cpp' '*.h' '*.qml'
   (no output)
   ```

   At this head the only occurrence is the pure-Python definition in
   `canopy_features/dock/display_change_response.py`. There is therefore no
   compiled host bridge at this base that can deliver a genuine KScreen or
   KWin signal to the new seam.

2. The compiled M2/M3 bridge on PR #754
   (`product/native-host-wiring-20261128`) is unmerged and adapts a different
   contract (`canopy_features/quick_controls/native_display_contract.py`).
   Using it here would require an owner/integrator decision about which
   implementation is authoritative; this workstream does not take it.

3. No authorized guest login, guest-additions channel or forwarded signal
   path was supplied for this task. No VM was started, mutated or probed by
   this worker, and no screenshot was captured.

## What was exercised instead

Bounded, headless `SYNTHETIC` fixtures only: 15 scenarios / 27 steps through
`tools/display_response/run_fixtures.py`, plus six tool-side unittests and the
existing 79 display tests at both the pinned base and the head. See
`evidence.json` and `targeted_tests_*.log` in this directory.

## Next action (owner-gated)

Wire the chosen compiled host adapter to one push call on a real KScreen
`configChanged`, KWin `screensChanged` or Qt logical-DPI signal, then run a
real Plasma guest with attached/detached displays and 100%/150%/200% scale
changes. Record exact head SHA, guest build, commands, raw logs and screenshots
before changing any runtime verdict.
