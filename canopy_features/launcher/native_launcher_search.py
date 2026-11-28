"""Bounded launcher search over the upstream native catalog wire bytes.

This is the M3 search/ranking composition. It does not build a second catalog
service: the desktop-entry read, parse, catalog ingest and ranking work are
performed by the existing owned primitives, and this module only consumes the
exact TSV wire bytes emitted by
:func:`canopy_features.launcher.native_catalog_producer.produce_catalog_bytes`.

Contract:
    ``search_native_catalog_bytes(wire, query)`` is pure, offline and stateless.
    ``search_native_directory(root, query)`` is the single read-only host entry
    point; it calls the one existing producer and then the pure function.

Neither entry point launches a process, opens a socket, starts a daemon, polls,
retains a cache, reads telemetry, implements a paid tier or changes the visible
desktop. Results are immutable and bounded; ranked order is total and
deterministic (match tier, within-tier position, name length, folded name,
catalog index). Every input is validated fail-closed with the module's domain
error, and no caller-supplied id, title or query is echoed into diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Tuple

from canopy_features.apps.launch_argv import DESKTOP_ID
from canopy_features.launcher.app_search_casefold import (
    MAX_QUERY_CHARS,
    normalize_for_search,
)
from canopy_features.launcher.app_search_ranking import rank_applications
from canopy_features.launcher.launcher_catalog_ingest import (
    MAX_ENTRIES,
    MAX_TITLE_CHARS,
)
from canopy_features.launcher.native_catalog_producer import (
    MAX_SNAPSHOT_BYTES,
    NativeCatalogError,
    produce_catalog_bytes,
)

MAX_RESULTS = 64

CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"
CLAIM_NO_NETWORK = "no_network"
CLAIM_NO_DUPLICATE_CATALOG_SERVICE = "no_duplicate_catalog_service"
CLAIM_NO_TELEMETRY = "no_telemetry"
CLAIM_NO_PAID_TIER = "no_paid_tier"
CLAIM_NO_PERSISTENT_STATE = "no_persistent_state"
CLAIM_NO_VISUAL_CHANGE = "no_visual_change"

FIXED_CLAIMS = (
    CLAIM_NO_DUPLICATE_CATALOG_SERVICE,
    CLAIM_NO_NETWORK,
    CLAIM_NO_PAID_TIER,
    CLAIM_NO_PERSISTENT_STATE,
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_TELEMETRY,
    CLAIM_NO_VISUAL_CHANGE,
)

# Same scalar categories the upstream parser and catalog ingest refuse. A wire
# carrying one of these could reintroduce text that the ingest contract already
# rejected, so the search boundary re-checks it before ranking.
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

__all__ = [
    "CLAIM_NO_DUPLICATE_CATALOG_SERVICE",
    "CLAIM_NO_NETWORK",
    "CLAIM_NO_PAID_TIER",
    "CLAIM_NO_PERSISTENT_STATE",
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_TELEMETRY",
    "CLAIM_NO_VISUAL_CHANGE",
    "FIXED_CLAIMS",
    "MAX_QUERY_CHARS",
    "MAX_RESULTS",
    "MAX_SNAPSHOT_BYTES",
    "NativeSearchError",
    "NativeSearchResult",
    "search_native_catalog_bytes",
    "search_native_directory",
]


class NativeSearchError(ValueError):
    """Invalid caller input or an upstream catalog the contract cannot rank."""


@dataclass(frozen=True)
class NativeSearchResult:
    """One ranked upstream catalog row, preserving its identity for the host.

    ``index`` is the row's position in the upstream catalog wire; a host can
    keep focus and selection aligned with the returned order without rebuilding
    the catalog.
    """

    app_id: str
    title: str
    tier: str
    score: int
    index: int


def _check_limit(limit):
    if type(limit) is not int or isinstance(limit, bool) or not 1 <= limit <= MAX_RESULTS:
        raise NativeSearchError("invalid result limit")


def _check_query(query):
    # normalize_for_search enforces exact str type, the query length cap, valid
    # Unicode and the NFKC/casefold bound. Its value is deliberately discarded:
    # rank_applications owns the tier semantics, this call is only the gate.
    try:
        normalize_for_search(query)
    except (ValueError, TypeError) as exc:
        raise NativeSearchError("invalid search query") from exc


def _decode_wire(wire):
    if type(wire) is not bytes:
        raise NativeSearchError("catalog wire must be bytes")
    if not wire or len(wire) > MAX_SNAPSHOT_BYTES:
        raise NativeSearchError("catalog wire is empty or exceeds the byte bound")
    try:
        text = wire.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise NativeSearchError("catalog wire is not valid UTF-8") from exc
    if not text.endswith("\n") or "\r" in text:
        raise NativeSearchError("catalog wire has an invalid line ending")
    lines = text.split("\n")[:-1]
    if not lines or len(lines) > MAX_ENTRIES:
        raise NativeSearchError("catalog wire row count is out of bounds")
    rows = []
    for line in lines:
        if line.count("\t") != 1:
            raise NativeSearchError("catalog wire row is not a two-field TSV record")
        app_id, title = line.split("\t", 1)
        if DESKTOP_ID.fullmatch(app_id) is None:
            raise NativeSearchError("catalog wire carries an invalid application id")
        if not title or len(title) > MAX_TITLE_CHARS:
            raise NativeSearchError("catalog wire carries an invalid title")
        if any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in title):
            raise NativeSearchError("catalog wire carries an unsafe title scalar")
        rows.append((app_id, title))
    return tuple(rows)


def search_native_catalog_bytes(wire, query, *, limit=MAX_RESULTS):
    """Rank the upstream catalog ``wire`` for ``query``, best match first.

    An empty or whitespace-only query returns the upstream rows in catalog
    order (tier ``all``). The wire is never modified and the result is always a
    bounded tuple, even when nothing matches.
    """
    _check_limit(limit)
    _check_query(query)
    rows = _decode_wire(wire)
    try:
        matches = rank_applications(query, tuple(title for _, title in rows))
    except (TypeError, ValueError) as exc:
        raise NativeSearchError("catalog titles could not be ranked") from exc
    return tuple(
        NativeSearchResult(
            app_id=rows[match.index][0],
            title=rows[match.index][1],
            tier=match.tier,
            score=match.score,
            index=match.index,
        )
        for match in matches[:limit]
    )


def search_native_directory(applications_dir, query, *, limit=MAX_RESULTS):
    """Produce the upstream catalog once, then search it.

    This is the only entry point that touches the host. It delegates the entire
    directory scan and desktop-entry parse to the existing producer, so there
    is one catalog reader and no duplicated enumeration. The upstream producer
    owns all desktop-entry access; this module adds no background service.
    """
    _check_limit(limit)
    _check_query(query)
    try:
        wire = produce_catalog_bytes(applications_dir)
    except NativeCatalogError as exc:
        raise NativeSearchError("native catalog is unavailable") from exc
    return search_native_catalog_bytes(wire, query, limit=limit)
