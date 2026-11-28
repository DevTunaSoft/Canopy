#!/usr/bin/env python3
"""Read-only GIO desktop-entry resolution probe for the Terminal dock IDs."""
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

IDS = (
    "gnome-terminal.desktop",
    "org.gnome.Terminal.desktop",
    "mate-terminal.desktop",
    "xfce4-terminal.desktop",
    "org.kde.konsole.desktop",
    "konsole.desktop",
)
for app_id in IDS:
    try:
        info = Gio.DesktopAppInfo.new(app_id)
    except Exception as exc:  # noqa: BLE001 - probe records absence, never crashes
        print("%s ABSENT %s" % (app_id, type(exc).__name__))
        continue
    if info is None:
        print("%s ABSENT None" % app_id)
        continue
    print("%s RESOLVED %s %s" % (
        app_id,
        bool(Gio.AppInfo.should_show(info)),
        Gio.AppInfo.get_commandline(info),
    ))
