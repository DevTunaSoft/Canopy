# Try Canopy Classic on Linux Mint Cinnamon (experimental)

This milestone is a **native desktop layout prototype**, not a standalone desktop environment, theme pack, installer or ISO. It reuses the existing Linux Mint Cinnamon desktop and its applets to minimize additional resident services. It is intended for a **disposable test account or virtual machine** first.

## Prerequisites
- Linux Mint running the **Cinnamon** desktop (not MATE or Xfce), single-monitor primary display, ordinary logged-in user.
- Python 3 and `gsettings` already available. No root privileges, network access, additional dependencies or background daemon required.
- Default Cinnamon configuration containing a bottom panel, native Menu and Grouped Window List. Customized and multi-monitor layouts deliberately fail closed.
- Use a test account. Back up personal settings separately before experimenting.

## Fetch/preview
Check out the feature branch `feat/classic-design-foundation` from [DevTunaSoft/Canopy](https://github.com/DevTunaSoft/Canopy). Run the following **inside a Cinnamon terminal**, from the repository root:

```bash
python3 tools/canopy_classic.py
```

This is read-only: it prints planned layout changes. If rejected, **do not force settings**. Record the current desktop, Cinnamon version and original values:

```bash
gsettings get org.cinnamon panels-enabled
gsettings get org.cinnamon enabled-applets
```

## Apply and undo
Only on a disposable test session, after inspecting preview output:

```bash
python3 tools/canopy_classic.py --apply
```

This creates an owner-only JSON backup at `~/.local/state/canopy/cinnamon-layout-backup.json` before changing any settings. It moves the Menu and system indicators to the top bar, and the native Grouped Window List to a new bottom panel. **This is an early visual structure, not a completed premium dock.** In the event of abnormal layout or missing applets, use:

```bash
python3 tools/canopy_classic.py --restore
```

If the desktop is inaccessible, open a terminal/TTY as the same user and restore the two recorded `org.cinnamon` GSettings keys manually from the JSON backup. Do not remove the backup until layout is restored. Applying again with an existing backup is blocked.

## Test and verify
```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q tools tests
```

Document the expected/actual layout, working menu/launchers/window switching, keyboard behavior, light/dark appearance, any crashes, multimonitor rejection, and settings backup/restore outcome. Capture **actual screenshots** and repeat baseline measurements according to `docs/PERFORMANCE.md` and `docs/VISUAL_QUALITY_GATE.md`.

## Explicit limitations
- Does not install or change the operating system, wallpaper, icons, theme, display manager, compositor, bootloader, or login flow.
- Does not reproduce a genuine macOS global application menu.
- No actual Linux session test results have been collected by this repository change.
- Applet behavior and visual polish are not yet proven on a supported Cinnamon release; test in a VM before normal workstation use.
- UI changes in this version are limited to native Cinnamon panels; premium visual styling will require further implementation.

## Next engineering increments
1. Verify native panel layout and rollback on an actual supported Linux Mint Cinnamon release.
2. Implement original, licensed Canopy iconography, color tokens and themes.
3. Integrate a correctly behaving centered dock using upstream Cinnamon components where practical.
4. Implement keyboard-accessible launcher behavior and refine window decoration.
5. Capture real screenshots, frame-time and idle-resource evidence; improve to meet quality gates.
