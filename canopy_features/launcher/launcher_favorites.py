"""Bounded persistent application favorites keyed by stable application IDs.

Offline, host-owned state helper for Canopy Classic's launcher. Favorites are
stored as a small versioned JSON list of stable IDs. Display names and
availability come from the host application catalog, never from this file, so
a renamed or installed app cannot silently change a favorite's identity.

This module is not a desktop service. It creates no threads, timers, sockets
or background processes, launches no applications, uses no network or paid
APIs, and touches only the state path supplied by its caller. All writes are
atomic and happen only on an explicit mutation. Any corrupt, oversized or
unsupported saved state is discarded so the store starts empty (fail-closed).

This is a modular component only. It does not prove a working desktop until a
host wires it into the compiled Qt application.
"""

import collections.abc
import json
import os
from pathlib import Path
import re
import tempfile

SCHEMA_VERSION = 1
MAX_FAVORITES = 16
MAX_ID_BYTES = 128
MAX_STATE_BYTES = 8192
APP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*", re.ASCII)


class FavoritesError(ValueError):
    """Invalid stable ID or unreadable favorites state."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FavoritesError("duplicate JSON key in favorites state")
        result[key] = value
    return result


def _reject_constant(value):
    raise FavoritesError("invalid JSON constant in favorites state")


def _installed_set(installed_ids):
    """Fail-closed conversion of a caller catalog into an installed-id set.

    A bare string is one id, not an iterable of ids: coercing it into a set
    turns every character into a fake catalog entry, so ``visible`` hides
    every favorite. Worse, ``prune`` would then persist that empty visible
    set and permanently erase the user's saved favorites. Mappings are
    refused for the same reason (iterating one silently uses only its keys),
    and unhashable entries collapse to this module's domain error instead of
    leaking a raw ``TypeError``.
    """
    if isinstance(installed_ids, (str, bytes, bytearray,
                                  collections.abc.Mapping)):
        raise FavoritesError("installed ids must be a collection of ids")
    try:
        iterator = iter(installed_ids)
    except TypeError as exc:
        raise FavoritesError("installed ids must be a collection of ids") from exc
    try:
        return frozenset(iterator)
    except TypeError as exc:
        raise FavoritesError("installed ids must be hashable") from exc


def valid_app_id(value):
    """True for a bounded, plain-ASCII stable application ID."""
    return (type(value) is str and 1 <= len(value) <= MAX_ID_BYTES
            and APP_ID.fullmatch(value) is not None)


class FavoritesStore:
    """Ordered, bounded favorites persisted atomically at ``path``.

    One host-owned instance per state file. Mutations save immediately; no
    polling or background writer exists. Corrupt saved state starts empty.
    """

    def __init__(self, path):
        if not isinstance(path, (str, os.PathLike)):
            raise FavoritesError("favorites state path must be a path")
        self._path = Path(path)
        self._ids = self._read()

    @property
    def path(self):
        return self._path

    def ids(self):
        """Immutable snapshot of favorites in display order."""
        return tuple(self._ids)

    def __len__(self):
        return len(self._ids)

    def add(self, app_id):
        """Append a stable ID; return True only when state changed.

        Duplicate IDs are ignored. A full store refuses new IDs and keeps all
        existing favorites.
        """
        if not valid_app_id(app_id):
            raise FavoritesError("invalid stable application ID")
        if app_id in self._ids or len(self._ids) >= MAX_FAVORITES:
            return False
        self._ids = (*self._ids, app_id)
        self._save()
        return True

    def remove(self, app_id):
        """Remove by stable ID; return True only when state changed."""
        if app_id not in self._ids:
            return False
        self._ids = tuple(item for item in self._ids if item != app_id)
        self._save()
        return True

    def visible(self, installed_ids):
        """Favorites still present in ``installed_ids``, in display order.

        Non-destructive: a temporarily empty catalog hides favorites without
        erasing them.
        """
        installed = _installed_set(installed_ids)
        return tuple(item for item in self._ids if item in installed)

    def prune(self, installed_ids):
        """Drop favorites absent from ``installed_ids``; return True if changed."""
        kept = self.visible(installed_ids)
        if kept == self._ids:
            return False
        self._ids = kept
        self._save()
        return True

    def _read(self):
        try:
            if self._path.stat().st_size > MAX_STATE_BYTES:
                return ()
            raw = self._path.read_bytes()
        except (OSError, ValueError):
            return ()
        try:
            state = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeError, ValueError):
            return ()
        if (type(state) is not dict or set(state) != {"version", "favorites"}
                or type(state["version"]) is not int
                or state["version"] != SCHEMA_VERSION):
            return ()
        items = state["favorites"]
        if type(items) is not list or len(items) > MAX_FAVORITES:
            return ()
        seen = set()
        for item in items:
            if not valid_app_id(item) or item in seen:
                return ()
            seen.add(item)
        return tuple(items)

    def _save(self):
        payload = json.dumps(
            {"favorites": list(self._ids), "version": SCHEMA_VERSION},
            ensure_ascii=True, separators=(",", ":"), sort_keys=True,
        ).encode("ascii")
        if len(payload) > MAX_STATE_BYTES:
            raise FavoritesError("favorites state exceeds byte bound")
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".favorites-", suffix=".tmp", dir=str(parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
