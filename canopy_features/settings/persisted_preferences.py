"""Fail-closed persisted preferences for Canopy Classic.

Pure host-side contract. It never probes hardware, starts a service, opens a
socket, spawns a process, guesses host state or writes outside the single
state path supplied by its caller. There is no default path and no daemon.

Every key is pinned to an existing configuration contract:

* ``reduced_motion`` uses the value domain of
  ``canopy_features.accessibility.reduced_motion_contract.PREFERENCES``.
* Unavailable settings reuse the fixed disclosure strings and reason codes of
  ``canopy_features.system.quick_controls_state`` rather than inventing new
  protocol text.
* The existing ``canopy_core.host_events`` topic set is checked for uniqueness
  and exact set equality with the pinned protocol-v2 set, so this module can
  never introduce a fifth private topic or accept a duplicated topic that
  hides an omitted approved one.

"Deciding is not executing": a view says whether a presentation may offer a
setting and why. The caller owns any persistence and any action. Corrupt,
duplicate-keyed, oversized or unknown state is discarded so the store starts
empty (fail closed), mirroring ``canopy_features.launcher.launcher_favorites``.
"""
from __future__ import annotations

import collections.abc
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping, Optional

from canopy_core.host_events import TOPICS as _HOST_EVENT_TOPICS
from canopy_features.accessibility import reduced_motion_contract as _motion
from canopy_features.system import quick_controls_state as _quick

__all__ = [
    "SCHEMA_VERSION",
    "MAX_STATE_BYTES",
    "MAX_KEY_BYTES",
    "REDUCED_MOTION_KEY",
    "KEYS",
    "PreferenceView",
    "PersistedPreferencesError",
    "PersistedPreferences",
    "HOST_EVENT_TOPICS",
    "checked_host_event_topics",
    "view_for_key",
]


SCHEMA_VERSION = 1
MAX_STATE_BYTES = 4096
MAX_KEY_BYTES = 64
MAX_KEYS = 16

REDUCED_MOTION_KEY = "reduced_motion"
UNSET = _motion.UNSET
_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")

# The host event protocol is fixed. The exact-set gate that enforces this is
# defined just below, after the module's domain error class.
# Fixed disclosures borrowed from the existing fail-closed quick-controls
# contract. No new reason code or free-form host string reaches the UI.
_NO_INTERFACE = _quick.DISCLOSURES[_quick.REASON_NO_HOST_INTERFACE]
_PRIVILEGED = _quick.DISCLOSURES[_quick.REASON_PRIVILEGED_HOST_CHANGE]
_BRIDGE_DISABLED = _quick.DISCLOSURES[_quick.REASON_BRIDGE_DISABLED]
_FROZEN_VISUAL = "Unavailable — approved visual identity is unchanged"


class PersistedPreferencesError(ValueError):
    """Invalid key, value, state document or storage boundary."""


# Protocol v2 pins exactly these four topics (docs/HOST_EVENT_CONTRACT.md).
_APPROVED_HOST_EVENT_TOPICS = frozenset({
    "app.catalog.changed",
    "window.state.changed",
    "session.state.changed",
    "capabilities.report",
})


def checked_host_event_topics(topics):
    """Return the approved immutable topic set, or fail closed on drift.

    A length test plus one membership test is not an exact-set claim: a source
    with a duplicated approved topic and another approved topic omitted keeps
    the same length and still has no private settings topic. Require both
    uniqueness and exact equality before any settings view can trust it.
    """
    if (isinstance(topics, (str, bytes, bytearray))
            or not isinstance(topics, collections.abc.Iterable)):
        raise PersistedPreferencesError("host event topics must be an iterable")
    try:
        entries = tuple(topics)
    except TypeError as exc:
        raise PersistedPreferencesError("invalid host event topics") from exc
    if any(type(entry) is not str for entry in entries):
        raise PersistedPreferencesError("invalid host event topic name")
    if len(set(entries)) != len(entries):
        raise PersistedPreferencesError("duplicate host event topic")
    if frozenset(entries) != _APPROVED_HOST_EVENT_TOPICS:
        raise PersistedPreferencesError(
            "host event topic set differs from the approved contract")
    return frozenset(entries)


try:
    HOST_EVENT_TOPICS = checked_host_event_topics(_HOST_EVENT_TOPICS)
except PersistedPreferencesError as exc:  # pragma: no cover - contract drift
    raise RuntimeError("host event topic contract drift in settings panel") from exc


class PreferenceView:
    """Immutable, renderable view of one preference.

    A view only describes availability. ``available`` is True for the single
    preference with a real consumer contract; every other key is a disclosed
    placeholder and can never be written.
    """

    __slots__ = ("key", "title", "value", "available", "disclosure", "source")

    def __init__(self, key, title, value, available, disclosure, source):
        self.key = key
        self.title = title
        self.value = value
        self.available = available
        self.disclosure = disclosure
        self.source = source

    def to_dict(self):
        return {
            "key": self.key,
            "title": self.title,
            "value": self.value,
            "available": self.available,
            "disclosure": self.disclosure,
            "source": self.source,
        }

    def __repr__(self):  # pragma: no cover - diagnostic only
        return "PreferenceView(%r)" % self.to_dict()


def _definition(key, title, values, available, disclosure, source):
    return {
        "key": key,
        "title": title,
        "values": frozenset(values),
        "available": available,
        "disclosure": disclosure,
        "source": source,
    }


_DEFINITIONS = {
    REDUCED_MOTION_KEY: _definition(
        REDUCED_MOTION_KEY,
        "Reduced motion",
        _motion.PREFERENCES,
        True,
        "Saved for the host; approved preview visuals do not change",
        "canopy_features.accessibility.reduced_motion_contract",
    ),
    "network": _definition("network", "Network", (), False, _NO_INTERFACE,
                           "canopy_features.system.quick_controls_state"),
    "audio": _definition("audio", "Sound", (), False, _NO_INTERFACE,
                         "canopy_features.system.quick_controls_state"),
    "power": _definition("power", "Power", (), False, _PRIVILEGED,
                         "canopy_features.system.quick_controls_state"),
    "session": _definition("session", "Session", (), False, _PRIVILEGED,
                           "canopy_features.system.quick_controls_state"),
    "shell_pack": _definition("shell_pack", "Shell pack", (), False,
                              _NO_INTERFACE, "docs/SHELL_PACK_ARCHITECTURE.md"),
    "notifications": _definition("notifications", "Notifications", (), False,
                                 _NO_INTERFACE, "docs/HOST_EVENT_CONTRACT.md"),
    "theme": _definition("theme", "Appearance", (), False, _FROZEN_VISUAL,
                         "AGENTS.md visual lock"),
}

KEYS = MappingProxyType({
    key: MappingProxyType(definition)
    for key, definition in _DEFINITIONS.items()
})


def _check_key(key):
    if type(key) is not str or not _KEY_PATTERN.fullmatch(key):
        raise PersistedPreferencesError("invalid preference key type")
    if key not in KEYS:
        raise PersistedPreferencesError("unknown preference key")
    return key


def view_for_key(key):
    """Fail-closed view for ``key`` without any stored value.

    Wrong types and unknown keys raise the module's domain error; no raw
    ``TypeError`` or host-supplied text can escape.
    """
    definition = KEYS[_check_key(key)]
    return PreferenceView(
        definition["key"],
        definition["title"],
        _motion.UNSET if definition["available"] else "",
        definition["available"],
        definition["disclosure"],
        definition["source"],
    )


def _no_duplicates(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise PersistedPreferencesError("duplicate key in preference state")
        result[name] = value
    return result


def _reject_constant(value):
    raise PersistedPreferencesError("invalid JSON constant in preference state")


def _validate_document(document):
    """Return a bounded value mapping or fail closed with an empty document."""
    if not isinstance(document, collections.abc.Mapping):
        return {}
    if set(document) - {"version", "values"}:
        return {}
    version = document.get("version", SCHEMA_VERSION)
    if type(version) is not int or version != SCHEMA_VERSION:
        return {}
    values = document.get("values", {})
    if not isinstance(values, collections.abc.Mapping):
        return {}
    if len(values) > MAX_KEYS:
        return {}
    checked = {}
    for key, value in values.items():
        if (type(key) is not str or len(key.encode("utf-8", "strict")) > MAX_KEY_BYTES
                or key not in KEYS):
            return {}
        definition = KEYS[key]
        if not definition["available"]:
            return {}
        if type(value) is not str or value not in definition["values"]:
            return {}
        checked[key] = value
    return checked


class PersistedPreferences:
    """Bounded, atomic preference store at a caller-supplied path.

    ``path`` must be a trusted, user-owned location chosen by the host. The
    constructor never creates directories and never writes; only an explicit
    successful :meth:`set` saves. A single instance owns one state file.
    """

    def __init__(self, path):
        if (isinstance(path, (bytes, bytearray)) or not isinstance(
                path, (str, os.PathLike))):
            raise PersistedPreferencesError("state path must be a path")
        self._path = Path(path)
        self._values = self._read()

    @property
    def path(self):
        return self._path

    def _read(self):
        try:
            raw = self._path.read_bytes()
        except (OSError, ValueError):
            return {}
        if len(raw) > MAX_STATE_BYTES:
            return {}
        try:
            document = json.loads(
                raw.decode("utf-8", "strict"),
                object_pairs_hook=_no_duplicates,
                parse_constant=_reject_constant,
            )
        except (UnicodeError, ValueError, TypeError):
            return {}
        return _validate_document(document)

    def _save(self):
        document = {
            "version": SCHEMA_VERSION,
            "values": dict(sorted(self._values.items())),
        }
        payload = json.dumps(document, sort_keys=True).encode("utf-8")
        if len(payload) > MAX_STATE_BYTES:
            raise PersistedPreferencesError("preference state exceeds byte cap")
        parent = self._path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(
                    "wb", dir=str(parent), prefix=".canopy-prefs-", delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(self._path))
        except OSError as exc:
            raise PersistedPreferencesError("could not persist preferences") from exc
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:  # pragma: no cover - best-effort cleanup
                    pass

    def view(self, key):
        _check_key(key)
        definition = KEYS[key]
        value = self._values.get(key, _motion.UNSET if definition["available"] else "")
        return PreferenceView(
            definition["key"],
            definition["title"],
            value,
            definition["available"],
            definition["disclosure"],
            definition["source"],
        )

    def snapshot(self):
        """Immutable point-in-time mapping of every preference view."""
        return MappingProxyType({key: self.view(key) for key in KEYS})

    def to_dict(self):
        return {key: self.view(key).to_dict() for key in KEYS}

    def set(self, key, value):
        """Persist one allowed value. Return False without writing when closed.

        Invalid types raise the domain error; unavailable keys and unknown
        values fail closed without changing durable state.
        """
        _check_key(key)
        if type(value) is not str:
            raise PersistedPreferencesError("preference value must be a string")
        definition = KEYS[key]
        if not definition["available"]:
            return False
        if value not in definition["values"]:
            raise PersistedPreferencesError("unsupported preference value")
        if self._values.get(key) == value:
            return True
        previous = dict(self._values)
        self._values[key] = value
        try:
            self._save()
        except PersistedPreferencesError:
            self._values = previous
            raise
        return True
