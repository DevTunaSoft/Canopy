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

The prototype displays a dark top bar with a Canopy menu and clock, plus a floating app dock with available Files/Web/Terminal entries and an Apps button. In Applications, type words from the application name or desktop entry ID to filter installed launchers. Press Enter in the search field to open the first match, or Down to focus the first match and use the arrow keys to select an app. You can also click an app or close the dialog with Escape. App activation uses Gio AppInfo. Missing applications are omitted. Open **Edit dock** from the Canopy menu to select up to 64 pinned applications. Unavailable saved pins appear in the editor so you can remove them. Save updates the dock immediately. The Apps entry stays available with an empty dock. Many pins scroll horizontally. Select **Quit preview** in the menu to exit.

**No autostart, desktop replacement, or background service is installed.** All windows close when the program exits. Preferences are loaded from `$XDG_CONFIG_HOME/canopy/settings.json` when that variable is an absolute path, or `~/.config/canopy/settings.json`. Missing settings use built-in defaults.

If the settings file is corrupt or unreadable, the preview reports its path and the error. Start a temporary recovery preview with `python3 -m canopy.classic_gtk --safe-defaults`. This uses built-in settings for that run and leaves the settings file untouched. Dock editing is unavailable in this temporary recovery mode.

## Known limits

- The menu button displays an original white penguin emblem. It shows the Canopy label if the SVG loader or artwork is unavailable.
- Panel/dock do not reserve screen space or replace existing Cinnamon panels.
- Not suitable for login-session use; no compositor or window management.
- At startup the panel and dock use the primary monitor’s work area. The dock sizes to its buttons. Monitor changes after startup, scaling, Cinnamon panel interaction and Wayland placement remain unverified.
- The dock's opaque fallback was inspected under Debian/Xvfb. Its composited transparency and rounded corners need target Mint visual review.
- Preliminary Debian/Xvfb process measurements are recorded in ADR-003. Target Mint measurements remain open.
- To exercise the launcher widgets with a virtual X11 display, run `xvfb-run -a /usr/bin/python3 -m unittest discover -s tests -v`. Linux Mint Cinnamon compatibility and screen-reader testing remain **NOT RUN**.
