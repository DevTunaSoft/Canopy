"""Versioned Classic preference configuration and bounded migration sources.

This is a pure host-side decision gate at the existing
:mod:`canopy_features.settings.persisted_preferences` boundary. It never opens,
reads, writes, renames or deletes a file; it never starts a service or probes
host state. A caller supplies the bytes it already owns, receives a canonical
current-version document, and keeps ownership of every persistence decision.
In particular, corrupt/unreadable/oversized state still follows the existing
quarantine contract: a migration decision is not permission to overwrite raw
bytes that the store could not inspect.

Two document shapes are defined (see ``docs/CLASSIC_CONFIG_SCHEMA_MIGRATION.md``):

* version 0 ("flat"): a bare mapping of preference keys to string values, with
  no ``version`` and no ``values`` wrapper. This is the only legacy source.
* version 1 ("versioned"): the current ``{"version": 1, "values": {...}}``
  shape written by ``PersistedPreferences``.

Every source has an immutable :class:`SourceContract` that pins its shape,
allowed keys, required keys, byte/key maxima and one named migration step.
Only contracts in :data:`SOURCE_CONTRACTS` can migrate, only forward, and only
within :data:`MAX_MIGRATION_HOPS` steps. Unknown, future, ambiguous,
duplicate-keyed, malformed, oversized or out-of-domain documents are refused
with :class:`ConfigSchemaMigrationError`; no file content reaches a message or
a log. Preference key names and value domains come from the existing
``persisted_preferences.KEYS`` contract, so this module cannot admit a setting
that the store would reject.
"""
from __future__ import annotations

import collections.abc
import json
import re
from types import MappingProxyType
from typing import NamedTuple

from canopy_features.settings import persisted_preferences as _prefs

__all__ = [
    "ConfigSchemaMigrationError",
    "CURRENT_SCHEMA_VERSION",
    "LEGACY_FLAT_VERSION",
    "MAX_STATE_BYTES",
    "MAX_KEY_BYTES",
    "MAX_KEYS",
    "MAX_MIGRATION_HOPS",
    "SourceContract",
    "SOURCE_CONTRACTS",
    "MIGRATION_STEPS",
    "source_contract",
    "migration_plan",
    "migrate_document",
]


class ConfigSchemaMigrationError(ValueError):
    """Unsupported schema version or violated bounded source contract."""


# Single source of truth: the store's own version, size and value domains.
CURRENT_SCHEMA_VERSION = _prefs.SCHEMA_VERSION
LEGACY_FLAT_VERSION = 0
MAX_STATE_BYTES = _prefs.MAX_STATE_BYTES
MAX_KEY_BYTES = _prefs.MAX_KEY_BYTES
MAX_KEYS = _prefs.MAX_KEYS
# A legacy document may traverse at most two named steps. The registry has one
# step today; the bound prevents a future chain from becoming unbounded.
MAX_MIGRATION_HOPS = 2

_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_AVAILABLE_KEYS = frozenset(
    key for key, definition in _prefs.KEYS.items() if definition["available"]
)


class SourceContract(NamedTuple):
    """Immutable declaration of one accepted source document shape."""

    version: int
    shape: str
    target_version: int
    allowed_keys: frozenset
    required_keys: frozenset
    max_keys: int
    max_bytes: int
    step: str


_SOURCE_CONTRACTS = {
    LEGACY_FLAT_VERSION: SourceContract(
        version=LEGACY_FLAT_VERSION,
        shape="flat",
        target_version=CURRENT_SCHEMA_VERSION,
        allowed_keys=_AVAILABLE_KEYS,
        required_keys=frozenset(),
        max_keys=MAX_KEYS,
        max_bytes=MAX_STATE_BYTES,
        step="flat_preferences_to_v1",
    ),
    CURRENT_SCHEMA_VERSION: SourceContract(
        version=CURRENT_SCHEMA_VERSION,
        shape="versioned",
        target_version=CURRENT_SCHEMA_VERSION,
        allowed_keys=_AVAILABLE_KEYS,
        required_keys=frozenset(),
        max_keys=MAX_KEYS,
        max_bytes=MAX_STATE_BYTES,
        step="",
    ),
}
SOURCE_CONTRACTS = MappingProxyType(_SOURCE_CONTRACTS)
MIGRATION_STEPS = MappingProxyType({
    version: contract.step
    for version, contract in _SOURCE_CONTRACTS.items()
    if contract.shape == "flat"
})


def _reject_constant(value):
    """Reject JSON's non-finite constants with the module's domain error."""
    raise ConfigSchemaMigrationError("invalid JSON constant in config source")


def _no_duplicates(pairs):
    """Reject duplicate object keys; json.loads otherwise keeps the last one."""
    result = {}
    for name, value in pairs:
        if name in result:
            raise ConfigSchemaMigrationError(
                "duplicate key in config source")
        result[name] = value
    return result


def source_contract(version):
    """Return the immutable contract for ``version`` or fail closed.

    ``bool`` is not an integer version: ``True`` must never select version 1.
    """
    if type(version) is not int or version not in SOURCE_CONTRACTS:
        raise ConfigSchemaMigrationError("unsupported config schema version")
    return SOURCE_CONTRACTS[version]


def migration_plan(version):
    """Return the bounded, ordered step names from ``version`` to current.

    A missing source, a backward/cyclic step or a chain longer than
    :data:`MAX_MIGRATION_HOPS` is refused. The result is a tuple, never a live
    or unbounded iterator.
    """
    if type(version) is not int:
        raise ConfigSchemaMigrationError("config schema version must be an int")
    current = version
    steps = []
    seen = set()
    while current != CURRENT_SCHEMA_VERSION:
        if current in seen:
            raise ConfigSchemaMigrationError("cyclic config migration source")
        seen.add(current)
        contract = SOURCE_CONTRACTS.get(current)
        if contract is None or contract.shape != "flat" or not contract.step:
            raise ConfigSchemaMigrationError(
                "no bounded migration source for config schema version")
        if contract.target_version <= current:
            raise ConfigSchemaMigrationError(
                "config migration source must move forward")
        steps.append(contract.step)
        if len(steps) > MAX_MIGRATION_HOPS:
            raise ConfigSchemaMigrationError(
                "config migration exceeds bounded hop count")
        current = contract.target_version
    return tuple(steps)


def _decode(raw):
    """Parse bounded UTF-8 JSON bytes without materializing unbounded input."""
    if isinstance(raw, str):
        try:
            data = raw.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise ConfigSchemaMigrationError(
                "config source is not encodable as UTF-8") from exc
    elif isinstance(raw, (bytes, bytearray)):
        data = bytes(raw)
    else:
        raise ConfigSchemaMigrationError("config source must be JSON bytes")
    if len(data) > MAX_STATE_BYTES:
        raise ConfigSchemaMigrationError("config source exceeds byte cap")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise ConfigSchemaMigrationError(
            "config source is not valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
        )
    except ConfigSchemaMigrationError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        # CPython raises plain ValueError for huge numeric literals, and
        # extremely deep nesting can raise RecursionError. Neither may escape
        # as a raw built-in exception from a fail-closed validator.
        raise ConfigSchemaMigrationError("invalid config source document") from exc


def _utf8_size(value):
    try:
        return len(value.encode("utf-8", "strict"))
    except (AttributeError, UnicodeError):
        return None


def _checked_values(values, contract):
    """Return a sorted, domain-checked copy of a source value mapping."""
    if not isinstance(values, collections.abc.Mapping):
        raise ConfigSchemaMigrationError("config values must be an object")
    if len(values) > contract.max_keys:
        raise ConfigSchemaMigrationError("config source exceeds key cap")
    checked = {}
    for key, value in values.items():
        if type(key) is not str or not _KEY_PATTERN.fullmatch(key):
            raise ConfigSchemaMigrationError("invalid config preference key")
        if key not in contract.allowed_keys:
            raise ConfigSchemaMigrationError("unknown config preference key")
        key_size = _utf8_size(key)
        if key_size is None or key_size > MAX_KEY_BYTES:
            raise ConfigSchemaMigrationError("invalid config preference key")
        if type(value) is not str:
            raise ConfigSchemaMigrationError("config preference value must be text")
        value_size = _utf8_size(value)
        if value_size is None:
            raise ConfigSchemaMigrationError("config preference value is not UTF-8")
        if value not in _prefs.KEYS[key]["values"]:
            raise ConfigSchemaMigrationError("unsupported config preference value")
        checked[key] = value
    if not contract.required_keys.issubset(checked):
        raise ConfigSchemaMigrationError("config source is missing required keys")
    return {key: checked[key] for key in sorted(checked)}


def _canonical(values):
    document = {
        "version": CURRENT_SCHEMA_VERSION,
        "values": _checked_values(values, source_contract(CURRENT_SCHEMA_VERSION)),
    }
    try:
        payload = json.dumps(document, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ConfigSchemaMigrationError(
            "migrated config cannot be encoded") from exc
    if len(payload) > MAX_STATE_BYTES:
        raise ConfigSchemaMigrationError("migrated config exceeds byte cap")
    return document


def migrate_document(raw):
    """Return a canonical current-version document for bounded source bytes.

    ``raw`` is JSON bytes (or text) already supplied by the caller. This
    function performs no I/O and never writes a file: it only decides what a
    safe current-version document would be. A current document is canonicalized
    (sorted values, exact fields); a version-0 flat document is migrated by its
    single registered step. Every other shape or version fails closed.
    """
    document = _decode(raw)
    if not isinstance(document, collections.abc.Mapping):
        raise ConfigSchemaMigrationError("config source must be an object")
    if "version" in document:
        version = document["version"]
        if type(version) is not int or version not in SOURCE_CONTRACTS:
            raise ConfigSchemaMigrationError("unsupported config schema version")
        if version != CURRENT_SCHEMA_VERSION:
            raise ConfigSchemaMigrationError(
                "only the flat legacy source may be migrated")
        if set(document) != {"version", "values"}:
            raise ConfigSchemaMigrationError("invalid current config shape")
        return _canonical(document["values"])
    if "values" in document:
        raise ConfigSchemaMigrationError(
            "ambiguous config source: values without a version")
    # No version and no wrapper: the flat legacy source. Its contract rejects
    # any unfamiliar key, so a foreign document cannot be laundered here.
    source_contract(LEGACY_FLAT_VERSION)
    migration_plan(LEGACY_FLAT_VERSION)
    return _canonical(document)


def _check_registry():
    """Fail at import if the pinned source registry drifts from its contract."""
    if (type(CURRENT_SCHEMA_VERSION) is not int
            or CURRENT_SCHEMA_VERSION <= 0
            or LEGACY_FLAT_VERSION >= CURRENT_SCHEMA_VERSION):
        raise RuntimeError("config schema version pin is invalid")
    if not 1 <= MAX_MIGRATION_HOPS <= 8:
        raise RuntimeError("config migration hop bound is invalid")
    if set(SOURCE_CONTRACTS) != {LEGACY_FLAT_VERSION, CURRENT_SCHEMA_VERSION}:
        raise RuntimeError("config source version set drift")
    for version, contract in SOURCE_CONTRACTS.items():
        if (contract.version != version
                or contract.shape not in ("flat", "versioned")
                or contract.target_version not in SOURCE_CONTRACTS
                or not isinstance(contract.allowed_keys, frozenset)
                or not isinstance(contract.required_keys, frozenset)
                or not contract.allowed_keys <= _AVAILABLE_KEYS
                or not contract.required_keys <= contract.allowed_keys
                or not 0 < contract.max_keys <= MAX_KEYS
                or not 0 < contract.max_bytes <= MAX_STATE_BYTES):
            raise RuntimeError("config source contract drift")
        if contract.shape == "versioned":
            if contract.target_version != version or contract.step:
                raise RuntimeError("current config contract drift")
        elif (contract.target_version <= version or not contract.step
              or version not in MIGRATION_STEPS):
            raise RuntimeError("legacy config migration contract drift")
    if len(migration_plan(LEGACY_FLAT_VERSION)) > MAX_MIGRATION_HOPS:
        raise RuntimeError("config migration chain exceeds its bound")


_check_registry()
