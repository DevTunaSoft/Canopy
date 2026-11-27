"""Durable, fail-closed pin-order state for the Canopy dock.

This is a pure host-side contract. It orders identifiers, reads and writes one
caller-supplied state file, and never draws a dock, edits approved artwork or
geometry, starts a service, opens a network endpoint or probes host state.
The host owns the trusted root and any presentation of the result.

A fresh instance over the same path is the restart boundary: it re-reads the
one state file and refuses corrupt, duplicated, oversized or unknown state by
starting empty instead of raising or applying partial data. The corrupt bytes
are left untouched until a later user action writes a clean, ordered state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePath
import re
import tempfile

from canopy_features.dock import dock_pinned_items as _pins
from canopy_features.security import path_jail_checks as _jail

__all__ = [
    "FORMAT_VERSION",
    "STATE_BASENAME",
    "USER_SEGMENT",
    "MAX_STATE_BYTES",
    "DockPinPersistenceError",
    "state_path_for_user",
    "DockPinStore",
]

FORMAT_VERSION = 1
STATE_BASENAME = "dock_pins.json"
USER_SEGMENT = "users"
MAX_STATE_BYTES = 4096

_ABSENT = "ABSENT"
_CORRUPT = "CORRUPT"
_OK = "OK"

# One conservative lowercase profile component: no separator, no leading
# dot, no case alias and no surrogate can become a second profile's path.
_USER_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z")
_TEMP_PREFIX = ".canopy-dock-pins-"


class DockPinPersistenceError(ValueError):
    """Invalid path, identifier, order or durable state document."""


def _path_text(value):
    """Return a str path or raise the domain error, never a built-in error."""
    if isinstance(value, (bytes, bytearray)) or not isinstance(
            value, (str, os.PathLike)):
        raise DockPinPersistenceError("dock pin state path must be a path")
    try:
        text = os.fspath(value)
    except Exception as exc:
        raise DockPinPersistenceError("invalid dock pin state path") from exc
    if not isinstance(text, str) or "\x00" in text:
        raise DockPinPersistenceError("invalid dock pin state path")
    return text


def _reject_linked_components(root, candidate):
    """Refuse a symlink at any existing component below ``root``."""
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise DockPinPersistenceError("dock pin state escapes its root") from exc
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                raise DockPinPersistenceError(
                    "symlink in dock pin state path")
            if not current.exists():
                break
        except OSError as exc:
            raise DockPinPersistenceError(
                "cannot inspect dock pin state path") from exc


def _resolve(root, path):
    """Return an absolute state path contained in the canonical ``root``."""
    try:
        root_real = _jail.canonicalize(root, must_exist=True)
    except _jail.PathJailError as exc:
        raise DockPinPersistenceError("invalid dock pin state root") from exc
    if not root_real.is_dir():
        raise DockPinPersistenceError("dock pin state root is not a directory")
    text = _path_text(path)
    if ".." in PurePath(text).parts:
        raise DockPinPersistenceError("dock pin state path must not contain '..'")
    try:
        candidate = _jail.resolve_within(root_real, text, must_exist=False)
    except _jail.PathJailError as exc:
        raise DockPinPersistenceError("dock pin state escapes its root") from exc
    _reject_linked_components(root_real, candidate)
    if not _jail.is_contained(candidate, root_real):
        raise DockPinPersistenceError("dock pin state escapes its root")
    return candidate, root_real


def state_path_for_user(root, user):
    """Return the isolated state path of one user under a trusted ``root``."""
    try:
        root_real = _jail.canonicalize(root, must_exist=True)
    except _jail.PathJailError as exc:
        raise DockPinPersistenceError("invalid dock pin state root") from exc
    if not root_real.is_dir():
        raise DockPinPersistenceError("dock pin state root is not a directory")
    if type(user) is not str or not _USER_PATTERN.fullmatch(user):
        raise DockPinPersistenceError("invalid dock pin user component")
    requested = root_real / USER_SEGMENT / user / STATE_BASENAME
    resolved, _ = _resolve(root_real, requested)
    return resolved


def _no_duplicates(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise DockPinPersistenceError("duplicate key in dock pin state")
        result[name] = value
    return result


def _reject_constant(value):
    raise DockPinPersistenceError("invalid JSON constant in dock pin state")


def _checked_id(app_id):
    """Return an identifier that is valid and encodable as UTF-8."""
    if type(app_id) is not str:
        raise DockPinPersistenceError("invalid dock pin identifier")
    try:
        app_id.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise DockPinPersistenceError(
            "unencodable dock pin identifier") from exc
    return app_id


def _decode(raw):
    """Return an immutable pin order from canonical bytes, or fail closed."""
    if len(raw) > MAX_STATE_BYTES:
        raise DockPinPersistenceError("dock pin state exceeds byte cap")
    try:
        document = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
        )
    except DockPinPersistenceError:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DockPinPersistenceError("invalid dock pin state JSON") from exc
    if (not isinstance(document, dict)
            or set(document) != {"version", "items"}):
        raise DockPinPersistenceError("unexpected dock pin state document")
    version = document["version"]
    if type(version) is not int or version != FORMAT_VERSION:
        raise DockPinPersistenceError("unsupported dock pin state version")
    items = document["items"]
    if type(items) is not list or len(items) > _pins.MAX_PINS:
        raise DockPinPersistenceError("invalid dock pin order")
    if any(type(item) is not str for item in items):
        raise DockPinPersistenceError("invalid dock pin identifier")
    try:
        state = _pins.PinnedItems(items=tuple(items))
        for item in items:
            _checked_id(item)
            _pins.contains(state, item)
    except ValueError as exc:
        raise DockPinPersistenceError("invalid dock pin order") from exc
    return state


class DockPinStore:
    """One atomic, per-profile store for the ordered pinned applications.

    ``root`` is mandatory: a trusted, existing caller-owned directory. The
    constructor never creates directories and never writes; only a successful
    pin, unpin or move saves. Read failures and corrupt state start empty.
    """

    def __init__(self, path, root=None):
        if root is None:
            raise DockPinPersistenceError("dock pin state root is mandatory")
        self._path, self._root = _resolve(root, path)
        self._state, self._status = self._read()

    @classmethod
    def for_user(cls, root, user):
        """Bind one isolated store to ``user`` under a trusted ``root``."""
        return cls(state_path_for_user(root, user), root=root)

    @property
    def path(self):
        return self._path

    @property
    def status(self):
        """``OK``, ``ABSENT`` or ``CORRUPT`` for the last read."""
        return self._status

    @property
    def state(self):
        return self._state

    def snapshot(self):
        """Immutable tuple of pinned identifiers in display order."""
        return self._state.items

    def reload(self):
        """Re-read from disk, modelling a host restart."""
        self._state, self._status = self._read()
        return self._state

    def _check_path(self):
        """Re-validate the jail immediately before every disk access."""
        self._path, self._root = _resolve(self._root, self._path)

    def _read(self):
        try:
            self._check_path()
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return _pins.empty(), _ABSENT
        except (DockPinPersistenceError, OSError, ValueError):
            return _pins.empty(), _CORRUPT
        try:
            return _decode(raw), _OK
        except DockPinPersistenceError:
            return _pins.empty(), _CORRUPT

    def _save(self):
        self._check_path()
        document = {
            "version": FORMAT_VERSION,
            "items": list(self._state.items),
        }
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_STATE_BYTES:
            raise DockPinPersistenceError("dock pin state exceeds byte cap")
        parent = self._path.parent
        temporary = None
        try:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                    "wb", dir=str(parent), prefix=_TEMP_PREFIX,
                    delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(self._path))
            temporary = None
        except OSError as exc:
            raise DockPinPersistenceError(
                "could not persist dock pin state") from exc
        finally:
            if temporary is not None:
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:  # pragma: no cover - best-effort cleanup
                    pass

    def _commit(self, updated):
        previous = self._state
        self._state = updated
        try:
            self._save()
        except Exception as exc:
            self._state = previous
            if isinstance(exc, DockPinPersistenceError):
                raise
            raise DockPinPersistenceError(
                "could not persist dock pin state") from exc
        self._status = _OK
        return True

    def pin(self, app_id):
        """Append one pin. Duplicates and over-cap adds are no-ops."""
        _checked_id(app_id)
        try:
            updated = _pins.add(self._state, app_id)
        except ValueError as exc:
            raise DockPinPersistenceError("invalid dock pin identifier") from exc
        if updated is self._state:
            return False
        return self._commit(updated)

    def unpin(self, app_id):
        """Remove one pin. A missing identifier is an idempotent no-op."""
        _checked_id(app_id)
        try:
            updated = _pins.remove(self._state, app_id)
        except ValueError as exc:
            raise DockPinPersistenceError("invalid dock pin identifier") from exc
        if updated is self._state:
            return False
        return self._commit(updated)

    def move(self, app_id, target_index):
        """Persist a clamped reorder of one existing pin."""
        _checked_id(app_id)
        try:
            updated = _pins.move(self._state, app_id, target_index)
        except ValueError as exc:
            raise DockPinPersistenceError("invalid dock pin move") from exc
        if updated is self._state:
            return False
        return self._commit(updated)
