"""Offline policy validation for Canopy Classic text scaling and font fallback.

Pure functions only: no timers, services, file I/O or background state.
Constants mirror the shipped Classic Qt prototype so this checker and the QML
do not silently drift apart. Results describe policy, not a running desktop.
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# Logical font pixel sizes used by prototype/classic/*.qml.
FONT_SIZES_PX: Tuple[int, ...] = (10, 11, 12, 13, 14, 19, 22)

MIN_READABLE_PX = 10           # smallest shipped base size
MAX_FITTING_PX = 22            # largest shipped base size, roomy layouts
MAX_FITTING_COMPACT_PX = 19    # PreviewWindow.qml condensed title size

MIN_TEXT_SCALE = 0.5
MAX_TEXT_SCALE = 3.0

COMPACT_WIDTH_PX = 800         # main.cpp: compact folder grid when width <= 800
CONDENSED_HEIGHT_PX = 390      # PreviewWindow.qml: condensed when height < 390
HIDPI_DPR = 1.5                # main.cpp: 150% scale device-pixel-ratio example
MAX_DPR = 4.0

GENERIC_FAMILY = "sans-serif"


@dataclass(frozen=True)
class Layout:
    compact: bool
    condensed: bool
    hidpi: bool

    @property
    def tight_fit(self) -> bool:
        return self.compact or self.condensed


@dataclass(frozen=True)
class ScaleReport:
    ok: bool
    base_px: float
    scale: float
    device_pixel_ratio: float
    logical_px: float
    physical_px: float
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class Fallback:
    ok: bool
    base_px: Optional[float]
    reason: str


def _finite_positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "'%s' must be a number" % name
    if not math.isfinite(value):
        return "'%s' must be finite" % name
    if value <= 0:
        return "'%s' must be greater than zero" % name
    return None


def classify_layout(width_px, height_px, device_pixel_ratio=1.0):
    """Classify a viewport against the Classic compact and HiDPI thresholds."""
    for name, value in (("width_px", width_px), ("height_px", height_px),
                        ("device_pixel_ratio", device_pixel_ratio)):
        error = _finite_positive(value, name)
        if error:
            raise ValueError(error)
    return Layout(
        compact=width_px <= COMPACT_WIDTH_PX,
        condensed=height_px < CONDENSED_HEIGHT_PX,
        hidpi=device_pixel_ratio >= HIDPI_DPR,
    )


def effective_pixels(base_px, scale, device_pixel_ratio=1.0):
    """Return (logical_px, physical_px) for one scaled Classic font size."""
    for name, value in (("base_px", base_px), ("scale", scale),
                        ("device_pixel_ratio", device_pixel_ratio)):
        error = _finite_positive(value, name)
        if error:
            raise ValueError(error)
    logical = base_px * scale
    return logical, logical * device_pixel_ratio


def validate_scale(scale):
    """Return problems with a text-scale factor; empty list means accepted."""
    error = _finite_positive(scale, "scale")
    if error:
        return [error]
    if not MIN_TEXT_SCALE <= scale <= MAX_TEXT_SCALE:
        return ["scale %.4g outside [%.4g, %.4g]" % (
            scale, MIN_TEXT_SCALE, MAX_TEXT_SCALE)]
    return []


def check_text(base_px, scale, layout, device_pixel_ratio=1.0):
    """Validate one scaled font size against readability and fitting bounds."""
    reasons = []
    for name, value in (("base_px", base_px), ("scale", scale),
                        ("device_pixel_ratio", device_pixel_ratio)):
        error = _finite_positive(value, name)
        if error:
            reasons.append(error)
    if not isinstance(layout, Layout):
        reasons.append("'layout' must be a Layout from classify_layout()")
    if isinstance(device_pixel_ratio, (int, float)) and not isinstance(
            device_pixel_ratio, bool) and math.isfinite(device_pixel_ratio) \
            and device_pixel_ratio > MAX_DPR:
        reasons.append("device pixel ratio exceeds %.4g" % MAX_DPR)
    if reasons:
        return ScaleReport(False, base_px, scale, device_pixel_ratio,
                           0.0, 0.0, tuple(reasons))

    reasons.extend(validate_scale(scale))
    logical, physical = effective_pixels(base_px, scale, device_pixel_ratio)
    maximum = MAX_FITTING_COMPACT_PX if layout.tight_fit else MAX_FITTING_PX
    if logical < MIN_READABLE_PX:
        reasons.append("effective %.4g px below readable minimum %.4g px" % (
            logical, MIN_READABLE_PX))
    if logical > maximum:
        reasons.append("effective %.4g px exceeds %s fitting cap %.4g px" % (
            logical, "compact" if layout.tight_fit else "standard", maximum))
    return ScaleReport(not reasons, base_px, scale, device_pixel_ratio,
                       logical, physical, tuple(reasons))


def _is_usable_font_size(value):
    """True only for finite, non-bool real numbers that can be ordered."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        # Arbitrarily large ints cannot be converted to float for ordering.
        return False


def resolve_fallback(base_px, scale, layout, available_sizes=FONT_SIZES_PX,
                     device_pixel_ratio=1.0):
    """Pick the closest available font size that satisfies the text policy.

    ``available_sizes`` is caller-supplied: an unhashable/non-iterable value or
    entries that are not finite, non-bool numbers cannot define a usable size
    and are skipped rather than raising a raw ``TypeError`` while sorting. With
    no usable size that fits, the documented no-fallback ``Fallback`` is
    returned, matching the empty-set and unsuitable-set behaviour.
    """
    error = _finite_positive(base_px, "base_px")
    if error:
        return Fallback(False, None, error)
    # A hostile, wrong-type scale cannot define a usable text scale. Fail
    # closed with the module's domain result before the value reaches %g
    # formatting in the no-fallback reason (which raised a raw TypeError).
    error = _finite_positive(scale, "scale")
    if error:
        return Fallback(False, None, error)
    if check_text(base_px, scale, layout, device_pixel_ratio).ok:
        return Fallback(True, float(base_px), "")
    # Only real, finite, non-bool numbers can be ordered by distance to
    # base_px; ignore unusable caller entries instead of leaking TypeError.
    try:
        iterator = iter(available_sizes)
    except TypeError:
        iterator = iter(())
    usable = [s for s in iterator if _is_usable_font_size(s)]
    for size in sorted(usable, key=lambda s: abs(s - base_px)):
        if check_text(size, scale, layout, device_pixel_ratio).ok:
            return Fallback(True, float(size),
                            "fell back from %g to %g px" % (base_px, size))
    return Fallback(False, None,
                    "no available font size fits scale %g for %s layout" % (
                        scale, "compact" if layout.tight_fit else "standard"))


def resolve_font_family(preferred, available, fallback=GENERIC_FAMILY):
    """Return the preferred family when installed, else a generic fallback."""
    if not isinstance(preferred, str) or not isinstance(fallback, str):
        raise ValueError("font families must be strings")
    if preferred and preferred in available:
        return preferred
    return fallback
