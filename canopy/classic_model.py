"""Pure presentation policy shared with the Classic GTK prototype."""
from dataclasses import dataclass
from datetime import datetime

from canopy.applications import visible_apps as visible_apps


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
