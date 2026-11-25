"""Bounded, Unicode-aware application-name matching primitive.

Pure standard-library matching for the Classic launcher. It does not load Qt,
launch processes, poll, open sockets, keep caches or hold state between calls.
A caller supplies a bounded candidate list and receives a bounded, deterministic
ranking. This module alone is not a working desktop; wiring it into the
compiled Qt application is a separate integration task.
"""
from dataclasses import dataclass
import unicodedata

MAX_QUERY_CHARS = 128
MAX_NAME_CHARS = 256
# NFKC can expand one code point into a compatibility sequence, so the
# normalized form needs its own bound beyond the 3x maximum of casefold.
MAX_NORMALIZED_QUERY_CHARS = 512
MAX_NORMALIZED_NAME_CHARS = 1024
MAX_CANDIDATES = 4096
MAX_RESULTS = 64

EXACT = 3
PREFIX = 2
SUBSTRING = 1
ANY = 0


class AppSearchError(ValueError):
    """Invalid, malformed or oversized application search input."""


@dataclass(frozen=True)
class Match:
    """One ranked candidate. Keeps the caller's original name and index."""

    name: str
    score: int
    index: int


def _normalize(text, max_chars, max_normalized, label):
    if type(text) is not str:
        raise AppSearchError(label + " must be a string")
    if len(text) > max_chars:
        raise AppSearchError(label + " exceeds " + str(max_chars) + " characters")
    try:
        text.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise AppSearchError(label + " is not valid Unicode") from exc
    key = unicodedata.normalize("NFKC", text.casefold()).strip()
    if len(key) > max_normalized:
        raise AppSearchError("normalized " + label + " exceeds bound")
    return key


def normalize_for_search(query):
    """Return the bounded caseless key for a launcher search query."""
    return _normalize(query, MAX_QUERY_CHARS, MAX_NORMALIZED_QUERY_CHARS, "query")


def normalize_name(name):
    """Return the bounded caseless key for one application name."""
    return _normalize(name, MAX_NAME_CHARS, MAX_NORMALIZED_NAME_CHARS, "name")


def matches(query, name):
    """Return True if the query occurs in the name after bounded normalization."""
    return normalize_for_search(query) in normalize_name(name)


def rank_matches(query, names, *, limit=MAX_RESULTS):
    """Rank bounded candidates as exact, prefix, substring, then input order.

    An empty query returns every candidate at score ANY, in input order.
    """
    if type(limit) is not int or isinstance(limit, bool) or not 1 <= limit <= MAX_RESULTS:
        raise AppSearchError("invalid result limit")
    if type(names) not in (tuple, list):
        raise AppSearchError("candidates must be a list or tuple")
    if len(names) > MAX_CANDIDATES:
        raise AppSearchError("candidate count exceeds bound")

    key = normalize_for_search(query)
    ranked = []
    for index, name in enumerate(names):
        name_key = normalize_name(name)
        if not key:
            score = ANY
        elif name_key == key:
            score = EXACT
        elif name_key.startswith(key):
            score = PREFIX
        elif key in name_key:
            score = SUBSTRING
        else:
            continue
        ranked.append(Match(name=name, score=score, index=index))
    ranked.sort(key=lambda match: (-match.score, match.index))
    return tuple(ranked[:limit])
