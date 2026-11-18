"""Pure presentation policy shared with the Classic GTK prototype."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DockItem:
    title: str
    desktop_id: str


DEFAULT_DOCK = (
    DockItem('Files', 'nemo.desktop'),
    DockItem('Web', 'firefox.desktop'),
    DockItem('Terminal', 'org.gnome.Terminal.desktop'),
)


def clock_label(now: datetime) -> str:
    """Local, short clock suitable for a compact top bar."""
    return now.strftime('%a %H:%M')


def visible_apps(apps):
    """Filter hidden or unnamed launchers and sort without duplicates."""
    result = {}
    for app in apps:
        if app.should_show() and app.get_name() and app.get_id():
            result.setdefault(app.get_id(), app)
    return sorted(result.values(), key=lambda app: (app.get_name().casefold(), app.get_id()))
