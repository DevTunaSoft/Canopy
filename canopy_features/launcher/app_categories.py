"""Freedesktop application category modelling and ordering.

Pure, offline, platform-independent data component. It models the
``Categories=`` field of a freedesktop.org desktop entry and orders
applications into the standard menu categories from the Desktop Menu
Specification. Reads no files, launches nothing, polls nothing, and imports
no Qt/GIO/OS-specific code. Wiring it into the compiled Classic Qt launcher
is separate integration work; this module alone is not a working desktop.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType

# Bounds keep work and memory bounded regardless of input size.
MAX_CATEGORY_ID_BYTES = 64
MAX_CATEGORY_TOKENS = 256
MAX_CATALOG_CATEGORIES = 128
# A launcher catalog must stay bounded no matter what iterable the host hands
# us.  Cap the number of consumed applications, not just the categories, so a
# hostile or runaway source cannot be fully materialized into ``decorated``.
MAX_APPLICATIONS = 4096

# Freedesktop category names: alphanumeric and '-' (vendor X- prefixes fit).
_CATEGORY_ID = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,%d}\Z" % (MAX_CATEGORY_ID_BYTES - 1))


class CategoryError(ValueError):
    """Invalid category input, bound violation, or duplicate category id."""


@dataclass(frozen=True)
class Category:
    """One freedesktop category: stable id, display label, canonical rank."""

    id: str
    display_name: str
    rank: int

    def __post_init__(self):
        if type(self.id) is not str or not _CATEGORY_ID.fullmatch(self.id):
            raise CategoryError("invalid category id")
        if type(self.display_name) is not str or not self.display_name:
            raise CategoryError("invalid category display name")
        if type(self.rank) is not int:
            raise CategoryError("invalid category rank")


@dataclass(frozen=True)
class Application:
    """A catalogued app: desktop-entry id, title, raw category id tokens."""

    id: str
    title: str
    categories: tuple

    def __post_init__(self):
        if type(self.id) is not str or not self.id:
            raise CategoryError("invalid application id")
        if type(self.title) is not str or not self.title:
            raise CategoryError("invalid application title")
        if not isinstance(self.categories, tuple):
            # A bare string is one category id, not a sequence of ids. tuple()
            # would silently explode it into single-character tokens and turn
            # a valid category into bogus unknown ones.
            if isinstance(self.categories, (str, bytes, bytearray)):
                raise CategoryError(
                    "application categories must be a tuple of category ids")
            try:
                object.__setattr__(self, "categories", tuple(self.categories))
            except TypeError:
                raise CategoryError(
                    "application categories must be iterable") from None
        if any(type(token) is not str or not _CATEGORY_ID.fullmatch(token)
               for token in self.categories):
            raise CategoryError("invalid application category token")


@dataclass(frozen=True)
class CategoryResolution:
    """Result of mapping raw category ids onto a catalog.

    ``known`` are catalog categories, deduplicated and canonically ordered.
    ``unknown`` are well-formed ids with no catalog entry (kept for callers to
    log or ignore, never silently converted into a category). ``reserved`` are
    freedesktop reserved ids that menus must ignore.
    """

    known: tuple
    unknown: tuple
    reserved: tuple

    @property
    def primary(self):
        """First known category by canonical rank, or None if all unknown."""
        return self.known[0] if self.known else None


# Ranks are spaced by 10 so callers can insert between them without renumber.
# Order follows the Desktop Menu Specification top-level menu sequence.
STANDARD_CATEGORIES = (
    Category("AudioVideo", "Multimedia", 10),
    Category("Audio", "Audio", 20),
    Category("Video", "Video", 30),
    Category("Development", "Development", 40),
    Category("Education", "Education", 50),
    Category("Game", "Games", 60),
    Category("Graphics", "Graphics", 70),
    Category("Network", "Internet", 80),
    Category("Office", "Office", 90),
    Category("Science", "Science", 100),
    Category("Settings", "Settings", 110),
    Category("System", "System", 120),
    Category("Utility", "Accessories", 130),
)

# Reserved by the specification; must not appear as menu categories.
RESERVED_CATEGORY_IDS = frozenset({"Screensaver", "TrayIcon", "Applets"})


def parse_categories(value):
    """Split a desktop-entry ``Categories=`` value into id tokens.

    Empty segments from trailing/duplicate ';' are dropped. Well-formed ids
    are returned in first-seen order; malformed tokens raise ``CategoryError``.
    Duplicates are preserved here and collapsed by ``CategoryCatalog.resolve``.
    """
    if value is None:
        return ()
    if type(value) is not str:
        raise CategoryError("Categories value must be a string")
    tokens = tuple(part.strip() for part in value.split(";") if part.strip())
    if len(tokens) > MAX_CATEGORY_TOKENS:
        raise CategoryError("too many category tokens")
    if any(not _CATEGORY_ID.fullmatch(token) for token in tokens):
        raise CategoryError("malformed category id in Categories value")
    return tokens


def order_categories(categories):
    """Return categories sorted by (rank, id); ids break rank ties."""
    return tuple(sorted(categories, key=lambda category: (category.rank, category.id)))


class CategoryCatalog:
    """Immutable set of known categories with duplicate-id rejection.

    Build from the standard set by default. ``categories`` replaces the base
    set; ``extra`` adds to it. Duplicate ids are rejected outright rather
    than resolving a winner, so a bad catalog fails closed.
    """

    def __init__(self, categories=None, *, extra=()):
        base = STANDARD_CATEGORIES if categories is None else tuple(categories)
        additions = tuple(extra)
        combined = base + additions
        if len(combined) > MAX_CATALOG_CATEGORIES:
            raise CategoryError("catalog exceeds category bound")
        by_id = {}
        for category in combined:
            if not isinstance(category, Category):
                raise CategoryError("catalog entries must be Category objects")
            if category.id in by_id:
                raise CategoryError("duplicate category id: " + category.id)
            by_id[category.id] = category
        self._by_id = MappingProxyType(by_id)

    @property
    def categories(self):
        return order_categories(self._by_id.values())

    def get(self, category_id):
        return self._by_id.get(category_id)

    def resolve(self, category_ids):
        """Map raw ids to known/unknown/reserved, deduplicating repeats."""
        if isinstance(category_ids, str) or not hasattr(category_ids, "__iter__"):
            raise CategoryError("category ids must be an iterable of strings")
        seen = set()
        tokens = []
        processed = 0
        for token in category_ids:
            if type(token) is not str or not _CATEGORY_ID.fullmatch(token):
                raise CategoryError("malformed category id")
            processed += 1
            if processed > MAX_CATEGORY_TOKENS:
                raise CategoryError("too many category ids")
            if token not in seen:
                seen.add(token)
                tokens.append(token)
        known, unknown, reserved = [], [], []
        for token in tokens:
            if token in RESERVED_CATEGORY_IDS:
                reserved.append(token)
            elif token in self._by_id:
                known.append(self._by_id[token])
            else:
                unknown.append(token)
        return CategoryResolution(
            known=order_categories(known),
            unknown=tuple(unknown),
            reserved=tuple(reserved),
        )


NO_CATEGORY_RANK = 1 << 30


def order_applications(applications, catalog):
    """Sort apps by primary category rank, then title, then id.

    Apps with no known category (only unknown/reserved tokens, or none) sort
    last but remain deterministic. Duplicate app ids are collapsed to the
    first occurrence so one desktop entry cannot occupy multiple slots.
    At most ``MAX_APPLICATIONS`` items are consumed; an oversized source fails
    closed with ``CategoryError`` instead of being fully materialized.
    """
    if not isinstance(catalog, CategoryCatalog):
        raise CategoryError("a CategoryCatalog is required")
    seen_ids = set()
    decorated = []
    processed = 0
    for app in applications:
        # Count every consumed item, including duplicates, so a generator that
        # keeps yielding cannot be drained without bound.
        processed += 1
        if processed > MAX_APPLICATIONS:
            raise CategoryError("too many applications")
        if not isinstance(app, Application):
            raise CategoryError("applications must be Application objects")
        if app.id in seen_ids:
            continue
        seen_ids.add(app.id)
        resolution = catalog.resolve(app.categories)
        primary = resolution.primary
        rank = primary.rank if primary is not None else NO_CATEGORY_RANK
        decorated.append(((rank, app.title.casefold(), app.id), app))
    return tuple(app for _, app in sorted(decorated, key=lambda item: item[0]))
