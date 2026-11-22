"""Offline validation of high-contrast color tokens.

Validates in-memory color token definitions against WCAG relative-luminance
contrast and accessible-naming rules. Pure and data driven: it never reads,
writes, or modifies artwork, QML, C++, wallpaper, dock geometry, or any file.
It starts no services, opens no sockets, polls nothing, and keeps all work
bounded by the size of the supplied token collection.

This is a modular component, not a desktop feature. Future integration is
still required: the compiled Qt application must call ``validate_option`` on
its high-contrast palette before applying it. Passing here does not prove a
working desktop, correct rendering, or real Linux Mint behavior.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

# WCAG 2.1 AAA threshold for normal text; appropriate for high contrast.
MIN_CONTRAST_RATIO = 7.0
MAX_TOKENS = 64
MAX_LABEL_LENGTH = 80

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


class HighContrastError(ValueError):
    """Raised for malformed token data or out-of-range validation inputs."""


@dataclass(frozen=True)
class ColorToken:
    """One high-contrast role with an accessible label and two hex colors."""

    label: str
    foreground: str
    background: str


@dataclass(frozen=True)
class HighContrastOption:
    """A named palette option made of bounded color role tokens."""

    name: str
    tokens: Tuple[ColorToken, ...]


@dataclass(frozen=True)
class TokenResult:
    """Validation outcome for one token; ``ratio`` is None if colors break."""

    label: str
    ratio: Optional[float]
    passed: bool
    problems: Tuple[str, ...]


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate outcome for one option, with every problem preserved."""

    name: str
    passed: bool
    results: Tuple[TokenResult, ...]
    problems: Tuple[str, ...]


def parse_hex_color(value):
    """Return an (r, g, b) tuple for #RGB or #RRGGBB, else raise.

    Alpha forms (#ARGB/#AARRGGBB) are rejected: contrast against an unknown
    composited background is indeterminate, so alpha cannot be validated.
    """
    if type(value) is not str:
        raise HighContrastError("color must be a string")
    if not value.startswith("#") or len(value) not in (4, 7):
        raise HighContrastError("color must be #RGB or #RRGGBB")
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    if any(char not in _HEX_DIGITS for char in digits):
        raise HighContrastError("color contains non-hex digits")
    return tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))


def relative_luminance(rgb):
    """WCAG 2.1 relative luminance for an (r, g, b) tuple in 0..255."""
    red, green, blue = rgb

    def channel(value):
        scaled = value / 255.0
        if scaled <= 0.04045:
            return scaled / 12.92
        return ((scaled + 0.055) / 1.055) ** 2.4

    return (0.2126 * channel(red) + 0.7152 * channel(green)
            + 0.0722 * channel(blue))


def _ratio(rgb_a, rgb_b):
    lum_a = relative_luminance(rgb_a)
    lum_b = relative_luminance(rgb_b)
    high, low = max(lum_a, lum_b), min(lum_a, lum_b)
    return (high + 0.05) / (low + 0.05)


def contrast_ratio(foreground, background):
    """Return the WCAG contrast ratio of two #RGB/#RRGGBB color strings."""
    return _ratio(parse_hex_color(foreground), parse_hex_color(background))


def _check_min_ratio(min_ratio):
    if type(min_ratio) not in (int, float) or not 1.0 <= min_ratio <= 21.0:
        raise HighContrastError("min_ratio must be a number in 1.0..21.0")


def validate_token(token, min_ratio=MIN_CONTRAST_RATIO):
    """Validate one token, collecting every problem instead of aborting."""
    if not isinstance(token, ColorToken):
        raise HighContrastError("token must be a ColorToken")
    _check_min_ratio(min_ratio)

    label = token.label
    problems = []
    if not isinstance(label, str) or not label.strip():
        problems.append("missing label")
        stored_label = ""
    else:
        stored_label = label[:MAX_LABEL_LENGTH]
        if len(label) > MAX_LABEL_LENGTH:
            problems.append("label too long")

    foreground = background = None
    try:
        foreground = parse_hex_color(token.foreground)
    except HighContrastError:
        problems.append("invalid foreground hex")
    try:
        background = parse_hex_color(token.background)
    except HighContrastError:
        problems.append("invalid background hex")

    ratio = None
    if foreground is not None and background is not None:
        ratio = round(_ratio(foreground, background), 2)
        if ratio < min_ratio:
            problems.append("contrast below minimum")

    return TokenResult(label=stored_label, ratio=ratio,
                       passed=not problems, problems=tuple(problems))


def validate_option(option, min_ratio=MIN_CONTRAST_RATIO):
    """Validate a bounded named palette option and return one report."""
    if not isinstance(option, HighContrastOption):
        raise HighContrastError("option must be a HighContrastOption")
    _check_min_ratio(min_ratio)
    if len(option.tokens) > MAX_TOKENS:
        raise HighContrastError("option exceeds %d tokens" % MAX_TOKENS)

    name = option.name
    problems = []
    if not isinstance(name, str) or not name.strip():
        problems.append("missing option name")
        stored_name = ""
    else:
        stored_name = name[:MAX_LABEL_LENGTH]
    if not option.tokens:
        problems.append("no tokens")

    results = tuple(validate_token(token, min_ratio) for token in option.tokens)
    for result in results:
        for problem in result.problems:
            problems.append("%s: %s" % (result.label or "<unnamed>", problem))

    return ValidationReport(
        name=stored_name,
        passed=not problems and all(result.passed for result in results),
        results=results,
        problems=tuple(problems),
    )
