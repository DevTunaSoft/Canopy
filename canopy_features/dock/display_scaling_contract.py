"""Logical-DPI scaling source contract for the Classic display-change boundary.

Pure Python decision input: no Qt, no GUI, no I/O, no polling, no thread and no
hardware observation. A trusted host supplies a physical pixel size and its
device scale when a real DPI signal arrives. This module only converts that
signal into bounded logical pixels; it never renders or edits presentation
source.
"""
import math

from canopy_features.dock.display_geometry_contract import round_half_up

EVENT_DPI_CHANGED = "dpi_changed"
MAX_SCALE = 4.0
MAX_PHYSICAL_DIMENSION = 7680
REASON_LOGICAL_DPI_CHANGED = "logical_dpi_changed"
REASON_LOGICAL_SIZE_UNCHANGED = "logical_size_unchanged"

__all__ = [
    "EVENT_DPI_CHANGED", "MAX_SCALE", "MAX_PHYSICAL_DIMENSION",
    "REASON_LOGICAL_DPI_CHANGED", "REASON_LOGICAL_SIZE_UNCHANGED",
    "DisplayScalingError", "validate_scale", "logical_size_from_physical",
]


class DisplayScalingError(ValueError):
    """Invalid scaling input; display observations are refused, not raised."""


def validate_scale(value):
    """Return a finite device scale in (0, 4], or fail closed."""
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 < value <= MAX_SCALE):
        raise DisplayScalingError("invalid display scale")
    return float(value)


def logical_size_from_physical(width, height, scale):
    """Convert bounded physical monitor pixels to logical Classic pixels.

    Physical extents are never compared against logical geometry: the same
    device can report 1920x1080 physical pixels at 150% scale and expose a
    1280x720 logical surface. Qt-style half-up rounding keeps the conversion
    deterministic at half pixels.
    """
    ratio = validate_scale(scale)
    for name, value in (("width", width), ("height", height)):
        if (type(value) is not int
                or not 1 <= value <= MAX_PHYSICAL_DIMENSION):
            raise DisplayScalingError("invalid physical " + name)
    return (round_half_up(width / ratio), round_half_up(height / ratio))
