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


def configured_dock_ids(preferences):
    """Resolve untouched settings to the Classic defaults."""
    if preferences.classic_pins is None:
        return [item.desktop_id for item in DEFAULT_DOCK]
    return preferences.classic_pins


def clock_label(now: datetime) -> str:
    """Local, short clock suitable for a compact top bar."""
    return now.strftime('%a %H:%M')


def dock_position(
    area_x: int, area_y: int, area_width: int, area_height: int,
    dock_width: int, dock_height: int, gap: int = 12,
) -> tuple[int, int]:
    """Center the dock at the bottom of the monitor's usable work area."""
    return (
        area_x + max(0, (area_width - dock_width) // 2),
        area_y + max(0, area_height - dock_height - gap),
    )
