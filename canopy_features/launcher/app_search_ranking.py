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
    """Smallest span containing query as an ordered subsequence, else None."""
    positions = []
    query_index = 0
    for char_index, char in enumerate(folded):
        if query_index < len(query) and char == query[query_index]:
            positions.append(char_index)
            query_index += 1
            if query_index == len(query):
                break
    if query_index != len(query):
        return None
    return positions[-1] - positions[0] + 1


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


def rank_applications(query: str, applications: Iterable[str]) -> Tuple[RankedMatch, ...]:
    """Rank ``applications`` against ``query``, best match first.

    ``applications`` is an iterable of titles (strings); each entry is read
    once and the input is never mutated. Empty or whitespace-only queries
    return every title in its original catalog order (tier ``all``), matching
    the launcher's clear-search behavior.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string")

    folded_query = query.strip().casefold()
    if not folded_query:
        return tuple(
            RankedMatch(name=name, tier=ALL, score=_TIER_RANK[ALL], index=index)
            for index, name in enumerate(applications)
        )

    ranked = []
    for index, name in enumerate(applications):
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
