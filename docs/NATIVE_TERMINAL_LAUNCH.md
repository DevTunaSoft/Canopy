# Native Terminal dock launch compatibility (M3, 2026-11-27)

## Change

Port the useful production part of PR #731 (head `2647930`) onto exact base
`ec910d7a7275296ecbc8b5e5c459d356205165d1`: the closed `Terminal` desktop-entry
allowlist in `prototype/classic/SystemAppLauncher.cpp` gains two fixed native IDs
after the four frozen ones:

- `org.kde.konsole.desktop`
- `konsole.desktop`

No wildcard, path, argv, URL, user input, runtime source, daemon, second GIO
path, QML, geometry, visual asset or persistent setting was added. The resulting
file SHA-256 is
`b397916b6e2b2dc2664972722a7a77185d80be7f52bc28325d3fc62f816e6a03`, byte-identical
to PR #731's version of that file. `SystemAppLauncher.h` is unchanged.

## Runtime verification (real KDE Plasma, stock desktop entries)

Guest: `Canopy-Test-Plasma6` (UUID `3aecd840-4dd6-4481-913f-64a289da406d`),
real X11 Plasma session (`startplasma-x11` PID 4656, `kwin_x11` PID 5384,
`plasmashell` PID 5422) on `DISPLAY=:0`, accessed through the existing NAT SSH
forward `127.0.0.1:2223` and the pre-existing scratch key. No password, VM
start/stop/snapshot/revert, package, desktop-entry, compositor or persistent
setting change was made.

The patched source was compiled **in guest scratch only** at
`/home/canopy/native_terminal_launch_20261127` with the same CMake/Ninja/Qt6
configuration as the prior build; binary SHA-256
`9bdcb7f525b0e8846b565484caf7e6e2211ef350dab77732b5d55b8536d84a8d`.
`--self-test-system-apps-capability` did **not** report `CANOPY_GIO_ENABLED`:
that probe aborted with `CAPABILITY_RC=134` because no Qt display was set
(`qt.qpa.xcb: could not connect to display`). No capability-probe result is
claimed. The native GIO launch path is instead evidenced by the real Konsole
activation below (stock desktop entry, D-Bus name and X window); that evidence
is `SCOPED_ON_GUEST_RUNTIME`, not CI acceptance.

Runtime command (host-orchestrated, guest-side script):

```sh
bash /home/canopy/native_terminal_launch_20261127/runtime/run_runtime.sh
```

Key output from the final run (`scratch/native_terminal_launch/runtime_evidence/runtime_console.log`,
SHA-256 `823a0e7420549de608b5e0cc3e8208d4c7167d0f0117c11e49dde2239f67f18b`):

```text
=== GIO LOOKUP (stock XDG data dirs) ===
gnome-terminal.desktop ABSENT TypeError
org.gnome.Terminal.desktop ABSENT TypeError
mate-terminal.desktop ABSENT TypeError
xfce4-terminal.desktop ABSENT TypeError
org.kde.konsole.desktop RESOLVED True konsole
konsole.desktop ABSENT TypeError
=== TERMINAL DOCK LAUNCH FIXTURE ===
CANOPY_TERMINAL_DOCK_NATIVE_LAUNCH_CONNECTED "Terminal"
CANOPY_TERMINAL_DOCK_REJECTED: unknown action
CANOPY_APP_LAUNCH_REQUESTED: "Terminal"
CANOPY_TERMINAL_DOCK_NATIVE_LAUNCH_REQUESTED
"TERMINAL_DOCK_LAUNCH_FIXTURE_PASS" dock signal reached the native GIO launcher
LAUNCH_RC=0
=== KONSOLE AFTER ===
19242 /usr/bin/konsole
=== DBUS AFTER ===
org.kde.konsole-19242  19242 konsole  canopy :1.100 user@1000.service
=== X WINDOWS AFTER ===
0x03600008  0 canopy-plasma6 ~ : bash — Konsole
  Geometry: 223x100
=== RESTORE ===
NO_KONSOLE
=== GUEST STOCK ENTRY UNCHANGED ===
cd15f8c829a7ae0edfb27d67920fcd2cafb252209c950ce2e5791b9d24d15d38  /usr/share/applications/org.kde.konsole.desktop
```

`konsole_window.png` (SHA-256 `2719513aa80ee5bb63f028daaba69700c17c8ebb4c6997bd5cad5dcd002c6e8c`)
shows the live `canopy@canopy-plasma6:~$` prompt. The guest-only Konsole process
was terminated during restore; `vm_before.png` and `vm_after.png` are
byte-identical (SHA-256 `39a47c62ff1400c8129ea2ba69223ce110f022ad7cbc05e340283d1e3c13c68c`).

**No duplicated service was used.** Unlike the earlier staged-entry evidence,
this run used the installed `/usr/share/applications/org.kde.konsole.desktop`
with stock XDG data directories; no scratch desktop entry, renamed copy,
`XDG_DATA_DIRS` override or substitute D-Bus activation service was created.

## Evidence and labels

- `scratch/native_terminal_launch/native_terminal_launch_runtime.json`: schema
  `canopy.native_terminal_launch_runtime/1`, verdict `PASS`, 9 PASS / 0 FAIL /
  3 NOT_RUN; exact runtime command, key output and SHA-256 for every artifact.
- `scratch/native_terminal_launch/runtime_evidence/SHA256SUMS.txt` verifies all
  captured artifacts.
- `SYNTHETIC`: nothing in this change is a microbenchmark; the only local checks
  were Python/unit/source-contract checks. `SCOPED_ON_GUEST_RUNTIME`: compiled
  binary and real Plasma/Konsole behavior on the dedicated guest.
  `NOT_RUN`: screen-reader/assistive-technology behavior, automatic CI-on-guest
  acceptance, and owner visual acceptance / release / merge.
- Resource impact: two extra `QStringLiteral` entries in a static closed list,
  evaluated only on an opt-in Terminal launch; no timer, thread, cache, daemon,
  polling or long-lived allocation was added. Real shell-owned PSS/CPU and
  compiled frame timings are `NOT_RUN`; no stability, security, accessibility
  or approved visual quality was traded away. No accessibility label was touched.

## Fake-GIO pin synchronization at this head

The dependent QA pins from PR #731 are now synchronized here against the
production source blob `b397916b…`:
`tools/qa/fake_gio_launch_fixture/expected-source-sha256.txt` (source digest),
`tools/qa/fake_gio_evidence_gate.py` (source digest and the 12-call
unavailable case) and
`tools/qa/fake_gio_launch_fixture/harness/system_app_launcher_fixture.cpp`
(12 `new` calls: six Terminal candidates walked by both `canLaunch()` and
`launch()`). These are QA contract updates only; production C++ and QML are
unchanged. No merge or self-approval is claimed in this draft.

## Local checks at head

```text
python3 tools/check_foundation.py -> PASS, rc=0
python3 -m unittest tests.test_classic_desktop_integration \
  tests.test_classic_remaining_dock_integration tests.test_fake_gio_evidence_gate
Ran 21 tests ... OK; rc=0
```
