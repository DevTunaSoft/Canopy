# Real Linux Mint guest acceptance: zero-change preflight

**Status:** A read-only readiness checker exists. No actual Linux Mint VM
acceptance has been executed or passed on GitHub. Ubuntu CI smoke tests are
not evidence of Linux Mint compatibility.

## Run inside an existing disposable Linux Mint VM

1. Boot the Mint guest with Cinnamon as the default session. Don't replace
   the display manager, compositor or login defaults.
2. From a Canopy checkout, run:

   ```sh
   python3 tools/mint_guest_preflight.py --json > mint-guest-preflight.json
   ```

3. READY_FOR_TESTS means Mint identity, graphical session, CMake, Ninja,
   pkg-config, xvfb-run and Qt6Core metadata were detected. It does NOT
   demonstrate that Qt compiled, a window launched or any artwork aligned.
   BLOCKED lists missing preconditions. The checker installs nothing.
4. Independently build the [Classic Qt prototype in draft PR #100](https://github.com/DevTunaSoft/Canopy/pull/100)
   or its verified successor, record exact source SHA and capture real Qt
   screenshots at 760x500, 1200x750, 1920x1080 and HiDPI.
5. With approved SHA-locked icons and cleared alpine wallpaper available,
   compare imagery against the latest visual decision. Confirm original
   images remain byte-exact and optical artwork alignment passes review.
6. For functional testing, [opt-in native app launching PR #102](https://github.com/DevTunaSoft/Canopy/pull/102)
   supports --enable-system-apps. Verify real Nemo, Firefox and Terminal
   in the Mint session, focus/close/relaunch and Cinnamon continuity.

## Session consistency checks

The read-only preflight now requires Linux Mint identity, a declared Cinnamon
desktop token (\`X-Cinnamon\` or \`Cinnamon\`, optionally inside a colon-separated
desktop list), and a recognized session type. For \`x11\`, \`DISPLAY\` must be
present; for \`wayland\`, \`WAYLAND_DISPLAY\` must be present. An unrelated
display variable, a \`tty\` session, or another desktop does not count.
Report fields identify only the category, never the raw environment values.

These checks are **environment consistency hints**; they cannot authenticate
the running compositor, establish that a display socket is usable, or prove
Linux Mint compatibility. \`READY_FOR_TESTS\` remains a prerequisite, not
a test pass. Real guest Qt compilation, runtime smoke, window behavior and
human visual acceptance must be validated separately.

## Evidence (separate from preflight)

- Mint release/session and tested source SHA.
- Qt build and application launch logs; screenshots and any QML warnings.
- Real native app launch behavior, keyboard focus and failure cases.
- Process PSS and five-minute idle CPU, measured on actual guest hardware.
- Reboot, snapshot rollback and original Cinnamon session recovery.
- PASS/FAIL/BLOCKED/NOT RUN status and explicit visual signoff.

The preflight reports no home directory, tokens, raw environment or user
data. Only categories, readiness booleans and generic Qt version are logged.
No VM pass may be claimed until an actual guest has been accessed and tested.

## Next in-guest smoke step

Once this preflight is READY_FOR_TESTS, use the dedicated
[Qt Classic guest smoke runner](MINT_CLASSIC_QT_SMOKE.md) with the *actual*
compiled prototype and exact original user-approved artwork. It captures
three resolution screenshots and source/binary hashes in an isolated
output folder. Unlike the preflight, it does launch the Qt preview for
a bounded self-test; it never changes default session ownership.

A green unit test of that script is **not actual Mint acceptance**.
Full functional, compositor, window-focus, stress, installation and
visual signoff remain separate release blockers.
