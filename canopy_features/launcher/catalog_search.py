"""Category-aware search over an already-ingested launcher catalog.

This refinement uses only rows from :class:`LauncherCatalogSnapshot`: no new
catalog entries are invented and no desktop database, filesystem, process,
timer or network source is read. Callers supply a query and an optional
category id; the module returns immutable, bounded results that keep each
row's ``app_id`` and existing category tokens alongside the existing ranking
tier from :mod:`app_search_ranking`.

Category ids are validated with the existing :func:`parse_categories` parser,
so hidden scalar laundering is refused there before a filter can be applied.
An unknown but well-formed id simply matches no rows. The module is pure and
stateless; it proves no compiled launch behavior or Mint acceptance.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from canopy_features.launcher.app_categories import (
    CategoryError,
    parse_categories,
)
from canopy_features.launcher.app_search_casefold import MAX_RESULTS
from canopy_features.launcher.app_search_ranking import rank_applications
from canopy_features.launcher.launcher_catalog_ingest import (
    MAX_ENTRIES,
    CatalogRow,
    LauncherCatalogSnapshot,
)

__all__ = [
    "MAX_RESULTS",
    "CatalogSearchError",
    "CatalogSearchResult",
    "search_catalog",
]


class CatalogSearchError(ValueError):
    """Invalid caller input to a catalog search."""


@dataclass(frozen=True)
class CatalogSearchResult:
    """One ranked catalog row, with its identity preserved for the host.

    ``index`` is the row's position in the filtered catalog list, matching
    the index emitted by ``rank_applications``; callers can therefore keep
    focus and selection aligned with the returned order.
    """

    app_id: str
    title: str
    categories: Tuple[str, ...]
    tier: str
    score: int
    index: int


def _category_token(value):
    if value is None:
        return None
    if type(value) is not str:
        raise CatalogSearchError("category must be a string or None")
    try:
        tokens = parse_categories(value)
    except CategoryError as exc:
        raise CatalogSearchError(str(exc)) from exc
    if len(tokens) != 1:
        raise CatalogSearchError("category must be one category id")
    return tokens[0]


def search_catalog(query, snapshot, *, category=None, limit=MAX_RESULTS):
    """Rank existing catalog rows for ``query``, optionally filtered by category.

    A blank query returns the filtered rows in catalog order. The result is
    always a bounded tuple and the caller's snapshot is never mutated.
    """
    if type(query) is not str:
        raise CatalogSearchError("query must be a string")
    if type(limit) is not int or isinstance(limit, bool) or not 1 <= limit <= MAX_RESULTS:
        raise CatalogSearchError("invalid result limit")
    category = _category_token(category)
    if not isinstance(snapshot, LauncherCatalogSnapshot):
        raise CatalogSearchError("an ingested catalog snapshot is required")
    rows = snapshot.rows
    if not isinstance(rows, (tuple, list)) or len(rows) > MAX_ENTRIES:
        raise CatalogSearchError("catalog rows exceed the ingest bound")

    selected = []
    for row in rows:
        if not isinstance(row, CatalogRow):
            raise CatalogSearchError("catalog rows must be ingested rows")
        if category is None or category in row.categories:
            selected.append(row)

    titles = tuple(row.title for row in selected)
    try:
        matches = rank_applications(query, titles)
    except (TypeError, ValueError) as exc:
        raise CatalogSearchError(str(exc)) from exc

    return tuple(
        CatalogSearchResult(
            app_id=selected[match.index].app_id,
            title=selected[match.index].title,
            categories=tuple(selected[match.index].categories),
            tier=match.tier,
            score=match.score,
            index=match.index,
        )
        for match in matches[:limit]
    )
