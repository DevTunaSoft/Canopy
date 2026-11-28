"""Read-only mirror of the owner-approved Classic dock geometry (32/96/14/7).

Pure Python only: no Qt import, no GUI, no filesystem read, no I/O, no thread,
no timer, no service and no hardware observation. The module never renders or
edits presentation source; it exists so tooling can prove that a headless
display-response change does not alter the frozen tuple.

Provenance: the tuple ``(32, 96, 14, 7)`` is the owner-approved restoration
recorded for PR #729 in the Rev3 directive (bar height, dock size, dock
padding, dock spacing). At the base of this worktree
(``ec910d7a7275296ecbc8b5e5c459d356205165d1``) the compiled
``prototype/classic/Theme.qml`` still carries an older mirror (32/88/12/7).
That divergence is deliberately reported, never repaired here: visual
restoration belongs to the owner-gated PR #729, not to an M4 decision module.
"""
import hashlib
import re
from dataclasses import dataclass

APPROVED_DOCK_GEOMETRY = (32, 96, 14, 7)
MAX_SOURCE_CHARS = 2_000_000
MAX_FIELD_VALUE = 10_000

__all__ = [
    "APPROVED_DOCK_GEOMETRY", "MAX_SOURCE_CHARS", "MAX_FIELD_VALUE",
    "GeometryContractError", "FrozenDockGeometry", "GeometryStatus",
    "APPROVED", "parse_theme_geometry", "geometry_status",
    "assert_approved",
]


class GeometryContractError(ValueError):
    """Invalid geometry input or a non-approved geometry tuple."""


@dataclass(frozen=True)
class FrozenDockGeometry:
    """The four frozen Classic dock scalars, in directive order."""

    bar_height: int
    dock_size: int
    dock_padding: int
    dock_spacing: int

    def __post_init__(self):
        for name in ("bar_height", "dock_size", "dock_padding",
                     "dock_spacing"):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= MAX_FIELD_VALUE:
                raise GeometryContractError("invalid geometry field " + name)

    def as_tuple(self):
        return (self.bar_height, self.dock_size, self.dock_padding,
                self.dock_spacing)

    @property
    def approved(self):
        return self.as_tuple() == APPROVED_DOCK_GEOMETRY

    def fingerprint(self):
        """Stable digest of the canonical approved-tuple spelling."""
        canonical = "/".join(str(part) for part in self.as_tuple()).encode("ascii")
        return hashlib.sha256(canonical).hexdigest()


APPROVED = FrozenDockGeometry(*APPROVED_DOCK_GEOMETRY)


@dataclass(frozen=True)
class GeometryStatus:
    """Read-only comparison of supplied source text with the approved tuple."""

    approved: tuple
    observed: tuple
    matches_approved: bool
    approved_fingerprint: str
    source_chars: int


_FIELD_PATTERNS = (
    ("bar_height", re.compile(
        r"^[ \t]*readonly[ \t]+property[ \t]+int[ \t]+barHeight"
        r"[ \t]*:[ \t]*([0-9]{1,5})[ \t]*\r?$", re.M)),
    ("dock_size", re.compile(
        r"^[ \t]*readonly[ \t]+property[ \t]+int[ \t]+dockSize"
        r"[ \t]*:[ \t]*([0-9]{1,5})[ \t]*\r?$", re.M)),
    ("dock_padding", re.compile(
        r"^[ \t]*readonly[ \t]+property[ \t]+int[ \t]+dockPadding"
        r"[ \t]*:[ \t]*([0-9]{1,5})[ \t]*\r?$", re.M)),
    ("dock_spacing", re.compile(
        r"^[ \t]*readonly[ \t]+property[ \t]+int[ \t]+dockSpacing"
        r"[ \t]*:[ \t]*([0-9]{1,5})[ \t]*\r?$", re.M)),
)


def parse_theme_geometry(source):
    """Parse one supplied QML text into a FrozenDockGeometry, or fail closed.

    ``source`` is caller-supplied text; this function never opens a file. A
    missing, duplicated or out-of-range property is rejected instead of
    guessing. Hostile oversized input is bounded before scanning.
    """
    if type(source) is not str or len(source) > MAX_SOURCE_CHARS:
        raise GeometryContractError("invalid theme source text")
    values = {}
    for name, pattern in _FIELD_PATTERNS:
        matches = pattern.findall(source)
        if len(matches) != 1:
            raise GeometryContractError("theme property not unique: " + name)
        value = int(matches[0])
        if not 0 < value <= MAX_FIELD_VALUE:
            raise GeometryContractError("theme property out of range: " + name)
        values[name] = value
    return FrozenDockGeometry(**values)


def geometry_status(source):
    """Compare supplied QML text with the approved tuple without editing it."""
    observed = parse_theme_geometry(source).as_tuple()
    return GeometryStatus(
        approved=APPROVED_DOCK_GEOMETRY,
        observed=observed,
        matches_approved=observed == APPROVED_DOCK_GEOMETRY,
        approved_fingerprint=APPROVED.fingerprint(),
        source_chars=len(source),
    )


def assert_approved(geometry):
    """Return the approved geometry, or refuse a different tuple."""
    if not isinstance(geometry, FrozenDockGeometry) or not geometry.approved:
        raise GeometryContractError("dock geometry is not the approved tuple")
    return geometry
