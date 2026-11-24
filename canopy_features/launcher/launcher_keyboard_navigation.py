"""Pure, bounded keyboard focus state for a Canopy launcher grid.

This module models focus decisions for trusted launcher results only. It does
not draw controls, read files, start services, poll, or change any approved
Canopy Classic visual element. All state is immutable and every collection is
bounded so stale or hostile input cannot grow memory.
"""
from __future__ import annotations

from dataclasses import dataclass

NO_FOCUS = -1
MAX_COLUMNS = 16
MAX_ITEMS = 256
MAX_QUERY = 256
MAX_ID_LENGTH = 128
GRID_DIRECTIONS = frozenset({"left", "right", "up", "down", "home", "end"})
SELECTION_DIRECTIONS = frozenset({"next", "previous", "home", "end"})


def _checked_columns(columns: int) -> int:
    """Return a valid column count or fail closed with the domain error.

    Both the validating factory and direct Grid construction rely on this one
    guard, so no divisibility-hostile instance can reach rows()/move().
    """
    if isinstance(columns, bool) or not isinstance(columns, int):
        raise ValueError("columns must be an integer")
    if not 1 <= columns <= MAX_COLUMNS:
        raise ValueError("columns out of range")
    return columns


@dataclass(frozen=True)
class Grid:
    """An immutable grid of trusted, unique application identifiers."""

    columns: int
    items: tuple[str, ...]

    def __post_init__(self) -> None:
        _checked_columns(self.columns)

    @property
    def rows(self) -> int:
        if not self.items:
            return 0
        return (len(self.items) + self.columns - 1) // self.columns


@dataclass(frozen=True)
class SearchSelection:
    """An immutable selection over the current, bounded result list."""

    results: tuple[str, ...]
    index: int = NO_FOCUS


def make_grid(items, columns: int) -> Grid:
    """Validate inputs and return a bounded grid; never mutate the caller."""
    _checked_columns(columns)
    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise ValueError("items must be a sequence of identifiers")
    if len(items) > MAX_ITEMS:
        raise ValueError("too many items")
    normalized = []
    for item in items:
        if not isinstance(item, str) or not item or len(item) > MAX_ID_LENGTH:
            raise ValueError("invalid item identifier")
        normalized.append(item)
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate item identifier")
    return Grid(columns=columns, items=tuple(normalized))


def focus_index(grid: Grid, requested: int) -> int:
    """Clamp a requested index into the grid, or NO_FOCUS when it is empty."""
    if not isinstance(grid, Grid):
        raise ValueError("grid must be a Grid")
    if isinstance(requested, bool) or not isinstance(requested, int):
        raise ValueError("requested must be an integer")
    if not grid.items:
        return NO_FOCUS
    return max(0, min(requested, len(grid.items) - 1))


def move(grid: Grid, index: int, direction: str) -> int:
    """Return the next focus index; movement clamps at grid and row edges."""
    if not isinstance(direction, str) or direction not in GRID_DIRECTIONS:
        raise ValueError("unsupported grid direction")
    current = focus_index(grid, index)
    if current == NO_FOCUS:
        return NO_FOCUS
    if direction == "home":
        return 0
    if direction == "end":
        return len(grid.items) - 1
    if direction == "left":
        row_start = (current // grid.columns) * grid.columns
        return max(row_start, current - 1)
    if direction == "right":
        row_start = (current // grid.columns) * grid.columns
        row_end = min(row_start + grid.columns - 1, len(grid.items) - 1)
        return min(row_end, current + 1)
    if direction == "up":
        return max(0, current - grid.columns)
    # Down in a compact final row clamps to the last real item, never to an
    # invisible placeholder cell.
    return min(len(grid.items) - 1, current + grid.columns)


def item_at(grid: Grid, index: int) -> str | None:
    """Return the identifier at a clamped index, or None for an empty grid."""
    current = focus_index(grid, index)
    if current == NO_FOCUS:
        return None
    return grid.items[current]


def make_selection(results, query: str = "") -> SearchSelection:
    """Validate a result list and select its first item, if any."""
    if not isinstance(query, str) or len(query) > MAX_QUERY:
        raise ValueError("invalid query")
    if isinstance(results, (str, bytes)) or not isinstance(results, (list, tuple)):
        raise ValueError("results must be a sequence of identifiers")
    if len(results) > MAX_ITEMS:
        raise ValueError("too many results")
    normalized = []
    for result in results:
        if not isinstance(result, str) or not result or len(result) > MAX_ID_LENGTH:
            raise ValueError("invalid result identifier")
        normalized.append(result)
    return SearchSelection(
        results=tuple(normalized),
        index=0 if normalized else NO_FOCUS,
    )


def move_selection(selection: SearchSelection, direction: str) -> SearchSelection:
    """Move the active result with clamped, deterministic bounds."""
    if not isinstance(selection, SearchSelection):
        raise ValueError("selection must be a SearchSelection")
    if not isinstance(direction, str) or direction not in SELECTION_DIRECTIONS:
        raise ValueError("unsupported selection direction")
    if not selection.results:
        return selection
    if direction == "home":
        index = 0
    elif direction == "end":
        index = len(selection.results) - 1
    elif direction == "next":
        index = min(len(selection.results) - 1, selection.index + 1)
    else:
        index = max(0, min(selection.index - 1, len(selection.results) - 1))
        if selection.index == NO_FOCUS:
            index = 0
    return SearchSelection(results=selection.results, index=index)


def selected_item(selection: SearchSelection) -> str | None:
    """Return the active identifier without inventing a result for no matches.

    NO_FOCUS is an explicit "nothing active" claim. A selection that carries
    it alongside results is contradictory input: clamping the sentinel to the
    first result would report a valid selection that the caller never made.
    Fail closed and let a real navigation set an index before claiming an item.
    """
    if not isinstance(selection, SearchSelection):
        raise ValueError("selection must be a SearchSelection")
    if selection.index == NO_FOCUS:
        return None
    if not selection.results:
        return None
    index = max(0, min(selection.index, len(selection.results) - 1))
    return selection.results[index]
