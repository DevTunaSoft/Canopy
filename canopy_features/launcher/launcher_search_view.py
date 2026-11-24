"""Compose bounded launcher ranking and keyboard focus into one host record.

Pure, offline and stateless: no Qt, no desktop database, no process launch, no
filesystem walk, no polling and no background work. Callers supply a search
query and a bounded sequence of application titles; this module returns one
immutable view that keeps the ranked result list and the focused item in strict
agreement. A trusted host can render the record or move focus without ever
recomputing which title an index refers to.

Ranking comes from :mod:`app_search_casefold`; focus state comes from
:mod:`launcher_keyboard_navigation`. Both are already bounded and tested. This
module adds the missing agreement gate: an index is accepted only when the
keyboard module resolves it to the same title the ranking module emitted.
Bad caller types, oversized inputs and any future disagreement fail closed with
``SearchViewError``. The module launches nothing and proves no running desktop.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from canopy_features.launcher.app_search_casefold import (
    MAX_RESULTS,
    AppSearchError,
    Match,
    normalize_for_search,
    rank_matches,
)
from canopy_features.launcher.launcher_keyboard_navigation import (
    NO_FOCUS,
    SearchSelection,
    make_selection,
    move_selection,
    selected_item,
)

STATUS_READY = "READY"
STATUS_EMPTY = "EMPTY"

__all__ = [
    "MAX_RESULTS",
    "STATUS_EMPTY",
    "STATUS_READY",
    "SearchView",
    "SearchViewError",
    "compose_search_view",
    "move_focus",
]


class SearchViewError(ValueError):
    """Invalid caller input or a broken ranking/focus agreement."""


@dataclass(frozen=True)
class SearchView:
    """One immutable, bounded view for the launcher host.

    ``key`` is the bounded caseless search key, ``results`` the ranked matches,
    and ``selected_name`` always equals ``results[selected_index].name`` unless
    the view is empty, in which case focus is ``NO_FOCUS`` and the name is None.
    """

    key: str
    results: Tuple[Match, ...]
    selected_index: int
    selected_name: Optional[str]
    status: str

    def to_dict(self) -> dict:
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "key": self.key,
            "results": [
                {"name": match.name, "score": match.score, "index": match.index}
                for match in self.results
            ],
            "selected_index": self.selected_index,
            "selected_name": self.selected_name,
            "status": self.status,
        }


def _integer(value, label):
    # type() rather than isinstance so bool cannot masquerade as an index.
    if type(value) is not int:
        raise SearchViewError(label + " must be an integer")
    return value


def _agree(selection, results, matches):
    """Return the selected name only when every source names the same title."""
    index = selection.index
    if not 0 <= index < len(results):
        return None
    name = selected_item(selection)
    if name is None or name != results[index] or name != matches[index].name:
        return None
    return name


def compose_search_view(query, names, *, focus=0, limit=MAX_RESULTS):
    """Rank ``names`` for ``query`` and bind a focused item to the result list.

    ``focus`` is clamped to the available results; an empty result list yields
    ``STATUS_EMPTY`` with no focus and no selected name. Invalid types and
    oversized inputs raise ``SearchViewError`` rather than being silently
    accepted. Neither the query nor the caller's name sequence is mutated.
    """
    focus = _integer(focus, "focus")
    limit = _integer(limit, "limit")
    if not 1 <= limit <= MAX_RESULTS:
        raise SearchViewError("limit out of range")

    try:
        key = normalize_for_search(query)
        matches = rank_matches(query, names, limit=limit)
    except AppSearchError as exc:
        raise SearchViewError(str(exc)) from exc

    results = tuple(match.name for match in matches)
    if not results:
        return SearchView(key, (), NO_FOCUS, None, STATUS_EMPTY)

    try:
        initial = make_selection(results, query=query)
    except ValueError as exc:
        raise SearchViewError(str(exc)) from exc

    index = max(0, min(focus, len(results) - 1))
    selection = SearchSelection(results=initial.results, index=index)
    chosen = _agree(selection, results, matches)
    if chosen is None:
        raise SearchViewError("ranking and focus state disagree")
    # A focus move must stay inside the same bounded result list.
    if _agree(move_selection(selection, "next"), results, matches) is None:
        raise SearchViewError("keyboard move left ranked bounds")
    return SearchView(key, matches, index, chosen, STATUS_READY)


def move_focus(view, direction):
    """Return a new view with focus moved; never mutate the supplied view.

    Moving an empty view is a no-op that returns the same immutable record.
    Unsupported directions and disagreement with the ranked list fail closed.
    """
    if not isinstance(view, SearchView):
        raise SearchViewError("view must be a SearchView")
    if view.status != STATUS_READY:
        return view
    if type(direction) is not str:
        raise SearchViewError("direction must be a string")

    results = tuple(match.name for match in view.results)
    try:
        # A host or replayed record can hand us a view that compose never
        # produced. Re-run the validating factory so duplicate result IDs do
        # not survive into a new READY view with a false navigation claim.
        checked = make_selection(results, query=view.key)
    except ValueError as exc:
        raise SearchViewError(str(exc)) from exc
    selection = SearchSelection(results=checked.results, index=view.selected_index)
    try:
        moved = move_selection(selection, direction)
    except ValueError as exc:
        raise SearchViewError(str(exc)) from exc
    chosen = _agree(moved, results, view.results)
    if chosen is None:
        raise SearchViewError("ranking and focus state disagree")
    return SearchView(view.key, view.results, moved.index, chosen, STATUS_READY)
