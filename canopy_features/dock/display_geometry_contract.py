"""Offline dock display-geometry contract for Canopy Classic.

Pure Python: no Qt, no GUI, no I/O, no background service. It models the frozen
Classic dock layout in logical (device-independent) pixels and checks it against
a screen size and a device pixel ratio. Useful for tooling and CI checks that
cannot start a compiled Qt window.

Frozen UI source of truth (read-only mirrors; these UI files are never edited):
  prototype/classic/Theme.qml     barHeight 32, dockSize 88, dockPadding 12,
                                  dockSpacing 7
  prototype/classic/DockTile.qml  tile width 58
  prototype/classic/Main.qml      root 1200x750, min 720x480, bottomMargin 22,
                                  dock centered, width = min(root.width - 32,
                                  row width + 2 * dockPadding)
  prototype/classic/main.cpp      fits/centers in logical space with 1px/2px
                                  tolerance; grabWindow() is physical pixels

Scale rule: QQuickWindow geometry is logical; QQuickWindow::grabWindow() returns
physical pixels (logical * device pixel ratio). Bounds and centering are checked
in logical space only. Physical extents are reported as evidence but never
compared against logical geometry (the 150% trap: 1200x750 logical becomes
1800x1125 physical).
"""

import math
from dataclasses import dataclass, field

# Read-only mirrors of frozen Classic geometry. See module docstring.
BAR_HEIGHT = 32
DOCK_HEIGHT = 88
DOCK_PADDING = 12
DOCK_SPACING = 7
TILE_WIDTH = 58
BOTTOM_MARGIN = 22
HORIZONTAL_CLAMP = 32

FIT_TOLERANCE = 1.0
CENTER_TOLERANCE = 2.0


def round_half_up(value):
    """Qt qRound semantics: .5 rounds away from zero, not banker's rounding."""
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class GeometryReport:
    """Bounds in both spaces plus ordered violation codes.

    Empty ``violations`` means the dock fits, clears the top bar and stays
    centered at the given screen size and scale.
    """

    logical: Rect
    physical: Rect
    screen_logical: Rect
    screen_physical: Rect
    violations: tuple = field(default_factory=tuple)

    @property
    def ok(self):
        return not self.violations


def dock_logical_rect(screen_width, screen_height, tile_count=8):
    """Expected Classic dock rectangle in logical pixels."""
    row_width = tile_count * TILE_WIDTH + max(0, tile_count - 1) * DOCK_SPACING
    dock_width = min(screen_width - HORIZONTAL_CLAMP,
                     row_width + 2 * DOCK_PADDING)
    return Rect(
        x=(screen_width - dock_width) / 2,
        y=screen_height - BOTTOM_MARGIN - DOCK_HEIGHT,
        width=dock_width,
        height=DOCK_HEIGHT,
    )


def to_physical(rect, scale):
    """Convert a logical rectangle to whole physical pixels."""
    return Rect(
        x=round_half_up(rect.x * scale),
        y=round_half_up(rect.y * scale),
        width=round_half_up(rect.width * scale),
        height=round_half_up(rect.height * scale),
    )


def validate_dock_bounds(screen_width, screen_height, scale=1.0,
                         tile_count=8, dock_rect=None):
    """Validate dock bounds against logical screen size and device scale.

    ``screen_width``/``screen_height`` are logical pixels, as QQuickWindow
    reports them. ``scale`` is the device pixel ratio. ``dock_rect``, when
    supplied, overrides the Classic layout for testing other geometry.
    Returns a GeometryReport; no exception is raised for invalid inputs.
    """
    violations = []
    scale_is_valid = math.isfinite(scale) and scale > 0
    if not scale_is_valid:
        violations.append("invalid_scale")
    effective_scale = scale if scale_is_valid else 1.0

    if screen_width <= 0 or screen_height <= 0:
        violations.append("invalid_screen")

    logical = dock_rect if dock_rect is not None else dock_logical_rect(
        screen_width, screen_height, tile_count)

    if logical.width <= 0 or logical.height <= 0:
        violations.append("dock_nonpositive")
    if logical.x < -FIT_TOLERANCE:
        violations.append("dock_left_out_of_bounds")
    if logical.x + logical.width > screen_width + FIT_TOLERANCE:
        violations.append("dock_right_out_of_bounds")
    if logical.y < 0:
        violations.append("dock_above_screen")
    elif logical.y < BAR_HEIGHT:
        violations.append("dock_overlaps_top_bar")
    if logical.y + logical.height > screen_height + FIT_TOLERANCE:
        violations.append("dock_bottom_out_of_bounds")
    if abs(logical.x + logical.width / 2 - screen_width / 2) > CENTER_TOLERANCE:
        violations.append("dock_not_centered")

    screen_logical = Rect(0, 0, screen_width, screen_height)
    return GeometryReport(
        logical=logical,
        physical=to_physical(logical, effective_scale),
        screen_logical=screen_logical,
        screen_physical=to_physical(screen_logical, effective_scale),
        violations=tuple(violations),
    )
