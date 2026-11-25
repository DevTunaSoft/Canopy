"""Offline WCAG contrast metrics for authored UI color references.

Parses the color reference forms used in Canopy Classic QML/SVG sources and
computes WCAG 2.x relative luminance, contrast ratio and AA/AAA ratings.

Scope: pure Python, no Qt, no display, no I/O and no background work. This is a
building block for an accessibility audit, not proof that the desktop renders
correctly. Translucent colors must be composited over an opaque background
before luminance is meaningful.
"""

from __future__ import annotations

import re
from typing import NamedTuple

__all__ = [
    "Color",
    "parse_color",
    "composite",
    "is_transparent",
    "relative_luminance",
    "contrast_ratio",
    "wcag_level",
    "meets_wcag",
    "audit_pair",
    "find_color_references",
]

# WCAG 2.x thresholds. Normal text uses 4.5:1 (AA) and 7:1 (AAA); large text
# uses 3:1 (AA) and 4.5:1 (AAA).
AA_NORMAL = 4.5
AA_LARGE = 3.0
AAA_NORMAL = 7.0
AAA_LARGE = 4.5


class Color(NamedTuple):
    """An sRGB color with channels and alpha in the closed range [0, 1]."""

    red: float
    green: float
    blue: float
    alpha: float = 1.0


# Bounded set of Qt/SVG color names seen in authored UI sources.
_NAMED_COLORS = {
    "transparent": Color(0.0, 0.0, 0.0, 0.0),
    "black": Color(0.0, 0.0, 0.0, 1.0),
    "white": Color(1.0, 1.0, 1.0, 1.0),
    "red": Color(1.0, 0.0, 0.0, 1.0),
    "green": Color(0.0, 0.5019607843137255, 0.0, 1.0),
    "blue": Color(0.0, 0.0, 1.0, 1.0),
    "yellow": Color(1.0, 1.0, 0.0, 1.0),
    "gray": Color(0.5019607843137255, 0.5019607843137255, 0.5019607843137255, 1.0),
    "grey": Color(0.5019607843137255, 0.5019607843137255, 0.5019607843137255, 1.0),
    "silver": Color(0.7529411764705882, 0.7529411764705882, 0.7529411764705882, 1.0),
    "orange": Color(1.0, 0.6470588235294118, 0.0, 1.0),
    "purple": Color(0.5019607843137255, 0.0, 0.5019607843137255, 1.0),
    "cyan": Color(0.0, 1.0, 1.0, 1.0),
    "aqua": Color(0.0, 1.0, 1.0, 1.0),
    "magenta": Color(1.0, 0.0, 1.0, 1.0),
    "fuchsia": Color(1.0, 0.0, 1.0, 1.0),
}

_HEX_RE = re.compile(r"#[0-9a-fA-F]+\Z")
_FUNC_RE = re.compile(r"(rgba?)\(\s*([^()]*)\)\Z", re.IGNORECASE)
# Longest alternatives first so a 8-digit Qt hex is not cut to 6 digits.
_REF_SCAN_RE = re.compile(
    r"(?<![0-9A-Fa-f])#(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{3})(?![0-9A-Fa-f])"
    r"|(?<![A-Za-z])rgba?\([^()]*\)"
    r"|(?<![A-Za-z])(?:transparent|black|white|red|green|blue|yellow|gray|grey|silver|orange|purple|cyan|aqua|magenta|fuchsia)(?![A-Za-z])",
    re.IGNORECASE,
)


def _channel(byte: int) -> float:
    return byte / 255.0


def parse_color(value: str) -> Color:
    """Parse an authored color reference into a :class:`Color`.

    Accepted forms: ``#RGB``, ``#ARGB``, ``#RRGGBB``, ``#AARRGGBB`` (Qt puts
    alpha first), ``rgb(r, g, b)``, ``rgba(r, g, b, a)`` with integer channels
    0-255 and alpha 0-255, and the bounded set of named colors including
    ``transparent``.

    Raises ``TypeError`` for non-string input and ``ValueError`` for malformed
    strings or out-of-range components.
    """
    if not isinstance(value, str):
        raise TypeError("color reference must be a string")
    text = value.strip()
    if not text:
        raise ValueError("empty color reference")

    lowered = text.lower()
    if lowered in _NAMED_COLORS:
        return _NAMED_COLORS[lowered]

    if _HEX_RE.fullmatch(text):
        digits = text[1:]
        if len(digits) == 3:
            r, g, b = (int(ch * 2, 16) for ch in digits)
            return Color(_channel(r), _channel(g), _channel(b))
        if len(digits) == 4:  # Qt #ARGB: alpha first.
            a, r, g, b = (int(ch * 2, 16) for ch in digits)
            return Color(_channel(r), _channel(g), _channel(b), _channel(a))
        if len(digits) == 6:
            r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
            return Color(_channel(r), _channel(g), _channel(b))
        if len(digits) == 8:  # Qt #AARRGGBB: alpha first.
            a, r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4, 6))
            return Color(_channel(r), _channel(g), _channel(b), _channel(a))
        raise ValueError(f"unsupported hex color length: {len(digits)}")

    match = _FUNC_RE.fullmatch(text)
    if match:
        parts = [part.strip() for part in match.group(2).split(",")]
        expected = 4 if match.group(1).lower() == "rgba" else 3
        if len(parts) != expected:
            raise ValueError(f"{match.group(1)}() expects {expected} components")
        try:
            values = [int(part, 10) for part in parts]
        except ValueError as exc:
            raise ValueError(f"non-integer component in {text}") from exc
        if any(part != str(num) for part, num in zip(parts, values)):
            raise ValueError(f"non-integer component in {text}")
        if any(number < 0 or number > 255 for number in values):
            raise ValueError(f"component outside 0-255 in {text}")
        channels = [_channel(number) for number in values]
        if expected == 3:
            channels.append(1.0)
        return Color(*channels)

    raise ValueError(f"unrecognized color reference: {value!r}")


def _as_color(value: str | Color) -> Color:
    if isinstance(value, Color):
        return value
    return parse_color(value)


def is_transparent(color: str | Color) -> bool:
    """Return True when the color is fully transparent (alpha is zero)."""
    return _as_color(color).alpha == 0.0


def composite(foreground: str | Color, background: str | Color) -> Color:
    """Source-over composite ``foreground`` onto an opaque ``background``.

    Raises ``ValueError`` if the background is translucent: no backdrop is
    defined, so the result would not be a meaningful screen color.
    """
    fg = _as_color(foreground)
    bg = _as_color(background)
    if bg.alpha != 1.0:
        raise ValueError("background must be opaque; composite it first")
    alpha = fg.alpha
    return Color(
        fg.red * alpha + bg.red * (1.0 - alpha),
        fg.green * alpha + bg.green * (1.0 - alpha),
        fg.blue * alpha + bg.blue * (1.0 - alpha),
        1.0,
    )


def relative_luminance(color: str | Color) -> float:
    """Return WCAG relative luminance in [0, 1] for an opaque color."""
    value = _as_color(color)
    if value.alpha != 1.0:
        raise ValueError("translucent color has no defined luminance; composite it first")

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * linear(value.red)
        + 0.7152 * linear(value.green)
        + 0.0722 * linear(value.blue)
    )


def contrast_ratio(foreground: str | Color, background: str | Color) -> float:
    """Return the WCAG contrast ratio in [1, 21] between two screen colors.

    A translucent foreground is composited over the background first. The
    background must be opaque.
    """
    bg = _as_color(background)
    fg = composite(foreground, bg) if _as_color(foreground).alpha != 1.0 else _as_color(foreground)
    light, dark = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def wcag_level(ratio: float, *, large_text: bool = False) -> str:
    """Return the strongest WCAG text level met: ``AAA``, ``AA`` or ``FAIL``."""
    if ratio < 0:
        raise ValueError("contrast ratio cannot be negative")
    if large_text:
        if ratio >= AAA_LARGE:
            return "AAA"
        return "AA" if ratio >= AA_LARGE else "FAIL"
    if ratio >= AAA_NORMAL:
        return "AAA"
    return "AA" if ratio >= AA_NORMAL else "FAIL"


def meets_wcag(ratio: float, *, level: str = "AA", large_text: bool = False) -> bool:
    """Return whether ``ratio`` meets ``level`` (``AA`` or ``AAA``)."""
    if level not in ("AA", "AAA"):
        raise ValueError("level must be 'AA' or 'AAA'")
    achieved = wcag_level(ratio, large_text=large_text)
    return achieved == "AAA" if level == "AAA" else achieved in ("AA", "AAA")


def audit_pair(
    foreground: str | Color,
    background: str | Color,
    *,
    large_text: bool = False,
) -> dict:
    """Return a compact audit record for one authored foreground/background pair."""
    ratio = contrast_ratio(foreground, background)
    return {
        "foreground": foreground,
        "background": background,
        "ratio": ratio,
        "level": wcag_level(ratio, large_text=large_text),
        "aa": meets_wcag(ratio, level="AA", large_text=large_text),
        "aaa": meets_wcag(ratio, level="AAA", large_text=large_text),
    }


def find_color_references(text: str) -> list[str]:
    """Extract ordered, distinct color references from authored source text.

    Recognizes hex, ``rgb()``/``rgba()`` and supported named colors. Malformed
    tokens such as five-digit hex are ignored rather than guessed.
    """
    if not isinstance(text, str):
        raise TypeError("source text must be a string")
    seen: set[str] = set()
    found: list[str] = []
    for match in _REF_SCAN_RE.finditer(text):
        token = match.group(0)
        if token not in seen:
            seen.add(token)
            found.append(token)
    return found
