"""Pure, immutable pinned-application order state for a Canopy dock.

This module owns ordering decisions only. It does not draw the dock, alter
approved geometry or artwork, read user files, or start services. Duplicate
and missing identifiers are idempotent no-ops so repeated user actions cannot
corrupt the pinned list. All collections are bounded.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_PINS = 64
MAX_ID_LENGTH = 128


@dataclass(frozen=True)
class PinnedItems:
    """An immutable, ordered tuple of unique trusted application IDs."""

    items: tuple[str, ...]

    def __post_init__(self) -> None:
        # A frozen dataclass still accepts any caller-supplied tuple. Reject
        # repeated trusted IDs here: a duplicate would look like a valid pin
        # order to consumers using contains()/index_of(). Malformed non-string
        # entries are left untouched for downstream consumers to deny.
        if not isinstance(self.items, tuple):
            return
        seen = set()
        for app_id in self.items:
            if not isinstance(app_id, str):
                continue
            if app_id in seen:
                raise ValueError("duplicate app_id")
            seen.add(app_id)


def empty() -> PinnedItems:
    return PinnedItems(items=())


def _valid_id(app_id: object) -> bool:
    return (isinstance(app_id, str) and bool(app_id)
            and len(app_id) <= MAX_ID_LENGTH
            and app_id == app_id.strip())


def contains(state: PinnedItems, app_id: str) -> bool:
    if not isinstance(state, PinnedItems):
        raise ValueError("state must be PinnedItems")
    if not _valid_id(app_id):
        raise ValueError("invalid app_id")
    return app_id in state.items


def add(state: PinnedItems, app_id: str) -> PinnedItems:
    """Append a pin; duplicates, invalid IDs and over-cap adds are no-ops."""
    if not isinstance(state, PinnedItems):
        raise ValueError("state must be PinnedItems")
    if not _valid_id(app_id):
        raise ValueError("invalid app_id")
    if app_id in state.items or len(state.items) >= MAX_PINS:
        return state
    return PinnedItems(items=state.items + (app_id,))


def remove(state: PinnedItems, app_id: str) -> PinnedItems:
    """Remove a pin; missing IDs are idempotent no-ops."""
    if not isinstance(state, PinnedItems):
        raise ValueError("state must be PinnedItems")
    if not _valid_id(app_id):
        raise ValueError("invalid app_id")
    if app_id not in state.items:
        return state
    return PinnedItems(items=tuple(item for item in state.items if item != app_id))


def move(state: PinnedItems, app_id: str, target_index: int) -> PinnedItems:
    """Move an existing pin to a clamped target index without duplicates."""
    if not isinstance(state, PinnedItems):
        raise ValueError("state must be PinnedItems")
    if not _valid_id(app_id):
        raise ValueError("invalid app_id")
    if isinstance(target_index, bool) or not isinstance(target_index, int):
        raise ValueError("target_index must be an integer")
    if app_id not in state.items:
        return state
    remaining = [item for item in state.items if item != app_id]
    index = max(0, min(target_index, len(remaining)))
    remaining.insert(index, app_id)
    return PinnedItems(items=tuple(remaining))


def index_of(state: PinnedItems, app_id: str) -> int:
    """Return the pin's position, or -1 when it is not pinned."""
    if not isinstance(state, PinnedItems):
        raise ValueError("state must be PinnedItems")
    if not _valid_id(app_id):
        raise ValueError("invalid app_id")
    try:
        return state.items.index(app_id)
    except ValueError:
        return -1


def apply_operations(state: PinnedItems, operations) -> PinnedItems:
    """Fold a bounded batch of ``(operation, app_id, target_index)`` tuples."""
    if isinstance(operations, (str, bytes)) or not isinstance(operations, (list, tuple)):
        raise ValueError("operations must be a sequence")
    if len(operations) > 1024:
        raise ValueError("too many operations")
    current = state
    for operation in operations:
        if not isinstance(operation, (tuple, list)) or not 2 <= len(operation) <= 3:
            raise ValueError("invalid operation")
        name, app_id = operation[0], operation[1]
        target = operation[2] if len(operation) == 3 else 0
        if name == "add":
            current = add(current, app_id)
        elif name == "remove":
            current = remove(current, app_id)
        elif name == "move":
            current = move(current, app_id, target)
        else:
            raise ValueError("unsupported operation")
    return current
