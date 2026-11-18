# Run the Canopy Classic preview (experimental)

This is an **optional preview application** inside an existing Linux Mint Cinnamon desktop, not a login session or installed desktop environment. It does not replace the Cinnamon panel.

## Requirements

On Linux Mint, have GTK3 Python introspection available (typically `python3-gi`, `gir1.2-gtk-3.0`) and a working graphical session. No root access is required to run the preview; package installation may request the normal administrator password.

## Try it

From the repository root in a graphical Cinnamon session:

```bash
python3 -m unittest discover -s tests -v
python3 -m canopy.classic_gtk
```

The prototype displays a dark top bar with a Canopy menu and clock, plus a floating app dock with available Files/Web/Terminal entries and an Apps button. In Applications, type words from the application name or desktop entry ID to filter installed launchers. Press Down to focus the first match, use the arrow keys to select an app, and press Enter to open it. You can also click an app or close the dialog with Escape. App activation uses Gio AppInfo. Missing applications are omitted. Select **Quit preview** in the menu to exit.

**No autostart, desktop replacement, or background service is installed.** All windows close when the program exits. Preferences are loaded from `$XDG_CONFIG_HOME/canopy/settings.json` when set, or `~/.config/canopy/settings.json`. Missing settings use safe defaults; corrupt settings intentionally raise an error instead of being overwritten.

## Known limits

- Menu uses text instead of final original white Tux art.
- Panel/dock do not reserve screen space or replace existing Cinnamon panels.
- Not suitable for login-session use; no compositor or window management.
- Layout and height are preliminary; multi-monitor, scaling and behavior under Wayland are **NOT RUN**.
- No measurements of startup/RAM/CPU have been recorded yet.
- To exercise the launcher widgets with a virtual X11 display, run `xvfb-run -a /usr/bin/python3 -m unittest discover -s tests -v`. Linux Mint Cinnamon compatibility and screen-reader testing remain **NOT RUN**.
