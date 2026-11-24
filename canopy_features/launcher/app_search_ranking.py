"""Deterministic ranking of launcher application-name matches.

Pure, offline and stateless: no Qt, no desktop database, no process launch, no
polling and no background services. This module only orders a caller-provided
catalog of application titles against a search query. A future Qt host may
feed the result into the launcher model; nothing here proves a running desktop.

Match tiers, best first:
    exact      - folded title equals the folded query
    prefix     - folded title starts with the folded query
    substring  - folded query appears anywhere in the folded title
    fuzzy      - folded query is an ordered subsequence (gaps allowed)
    all        - empty/whitespace-only query: every title, catalog order

Ordering is fully deterministic: tier, then match position/tightness, then
shorter title, then case-folded title, then original catalog index. Ties never
depend on dict/set iteration or sort stability.
"""

from dataclasses import dataclass
from typing import Iterable, Tuple

EXACT = "exact"
PREFIX = "prefix"
SUBSTRING = "substring"
FUZZY = "fuzzy"
ALL = "all"

# Higher tier rank means a better match. Never change the relative order.
_TIER_RANK = {EXACT: 4, PREFIX: 3, SUBSTRING: 2, FUZZY: 1, ALL: 0}

__all__ = [
    "RankedMatch",
    "rank_applications",
    "EXACT",
    "PREFIX",
    "SUBSTRING",
    "FUZZY",
    "ALL",
]


@dataclass(frozen=True)
class RankedMatch:
    """One catalog entry with its match tier and original position."""

    name: str
    tier: str
    score: int
    index: int


def _subsequence_span(query: str, folded: str):
    """Smallest span containing query as an ordered subsequence, else None.

    Greedy leftmost matching is not span-minimal when query characters repeat
    (e.g. ``ab`` in ``aab`` has span 2, not 3). For each query prefix track the
    *latest* start index that can realize it; the rightmost start leaves the
    shortest possible window. Iterate prefix indices in reverse so an update
    at this character cannot reuse the same character for two prefix steps.
    """
    if not query:
        return 0
    # Rightmost start index that can realize each matched query prefix.
    latest_start: list[int | None] = [None] * len(query)
    best = None
    for char_index, char in enumerate(folded):
        for prefix in range(len(query) - 1, -1, -1):
            if char != query[prefix]:
                continue
            if prefix == 0:
                latest_start[0] = char_index
            elif latest_start[prefix - 1] is not None:
                latest_start[prefix] = latest_start[prefix - 1]
        if latest_start[-1] is not None:
            span = char_index - latest_start[-1] + 1
            if best is None or span < best:
                best = span
    return best


def _classify(query: str, folded: str):
    """Return (tier, within-tier key) for a folded title, or None."""
    if folded == query:
        return EXACT, 0
    if folded.startswith(query):
        return PREFIX, 0
    position = folded.find(query)
    if position >= 0:
        return SUBSTRING, position
    span = _subsequence_span(query, folded)
    if span is not None:
        return FUZZY, span
    return None


def _iter_titles(applications):
    """Yield ``(index, title)`` after enforcing the catalog's type contract.

    A bare ``str``/``bytes``/``bytearray`` would be enumerated into
    single-character "titles", so it is refused. Non-iterable catalogs and
    non-string titles raise ``TypeError`` rather than leaking a raw
    ``AttributeError`` from ``casefold``. The title check is exact-type: a
    ``str`` subclass may override ``casefold`` to return a non-string or raise,
    which would otherwise leak a raw exception on the filter path and smuggle
    a malformed label into a valid-looking match on the empty-query path.
    Both paths use this helper so they agree on the contract.
    """
    if isinstance(applications, (str, bytes, bytearray)):
        raise TypeError("applications must be an iterable of title strings")
    try:
        iterator = iter(applications)
    except TypeError:
        raise TypeError("applications must be an iterable of title strings") from None
    for index, title in enumerate(iterator):
        if type(title) is not str:
            raise TypeError(
                "application title at index %d must be a string" % index)
        yield index, title


def rank_applications(query: str, applications: Iterable[str]) -> Tuple[RankedMatch, ...]:
    """Rank ``applications`` against ``query``, best match first.

    ``applications`` is an iterable of titles (exact ``str``, not a
    duck-typed subclass); each entry is read once and the input is never
    mutated. Empty or whitespace-only queries return every title in its
    original catalog order (tier ``all``), matching the launcher's
    clear-search behavior.
    """
    if type(query) is not str:
        raise TypeError("query must be a string")

    folded_query = query.strip().casefold()
    if not folded_query:
        return tuple(
            RankedMatch(name=name, tier=ALL, score=_TIER_RANK[ALL], index=index)
            for index, name in _iter_titles(applications)
        )

    ranked = []
    for index, name in _iter_titles(applications):
        folded_name = name.casefold()
        classified = _classify(folded_query, folded_name)
        if classified is None:
            continue
        tier, within_key = classified
        # Ascending sort key: lower is better. Key is total, so ties are stable
        # across runs, platforms and Python hash seeds.
        sort_key = (
            -_TIER_RANK[tier],
            within_key,
            len(folded_name),
            folded_name,
            index,
        )
        ranked.append((sort_key, RankedMatch(
            name=name, tier=tier, score=_TIER_RANK[tier], index=index)))

    ranked.sort(key=lambda item: item[0])
    return tuple(match for _, match in ranked)
