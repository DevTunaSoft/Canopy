"""Pure, bounded source-contract for Classic launcher desktop-entry enumeration.

This module describes the *sources* a launcher enumeration may use. The caller
supplies a finite, ordered sequence of source descriptors; this module returns
one immutable, deterministic snapshot of the accepted sources with fixed
negative claims. It performs no filesystem access, no directory scan, no
process launch, no polling, no timer, no network, no cache retention and no
visual work. It neither reads a real host path nor claims a running desktop.

This is deliberately a source-contract layer, distinct from:

* the native catalog refresh bridge (PR #694), which converts host events into
  producer calls and bytes; and
* the compiled-runtime catalog refresh boundary characterization (PR #696),
  which records what a running Classic process cannot reload.

Those concerns consume a source list; this module only defines its safe,
bounded shape. Every refusal is fail-closed: no partial snapshot is returned
and no caller-supplied text is copied into diagnostics.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import ntpath
import posixpath
from typing import Tuple
import unicodedata

MAX_SOURCES = 8
MAX_PATH_CHARS = 512
MAX_ENTRIES_PER_SOURCE = 512
MAX_TOTAL_ENTRIES = 1024

ROLE_EXPLICIT = "explicit"
ROLE_XDG_DATA_DIRS = "xdg_data_dirs"
ROLE_XDG_DATA_HOME = "xdg_data_home"
ALLOWED_ROLES = (ROLE_EXPLICIT, ROLE_XDG_DATA_DIRS, ROLE_XDG_DATA_HOME)

_DESCRIPTOR_KEYS = frozenset({"role", "path", "max_entries"})
_UNSAFE_UNICODE_CATEGORIES = frozenset(
    {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

CLAIM_NO_IMPLICIT_DISCOVERY = "no_implicit_discovery"
CLAIM_NO_SYMLINK_FOLLOW = "no_symlink_follow"
CLAIM_NO_RECURSIVE_WALK = "no_recursive_walk"
CLAIM_NO_DUPLICATE_SOURCES = "no_duplicate_sources"
CLAIM_NO_UNBOUNDED_GROWTH = "no_unbounded_growth"
CLAIM_NO_FILESYSTEM_IO = "no_filesystem_io"
CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"
CLAIM_NO_VISUAL_CHANGE = "no_visual_change"

FIXED_CLAIMS = (
    CLAIM_NO_IMPLICIT_DISCOVERY,
    CLAIM_NO_SYMLINK_FOLLOW,
    CLAIM_NO_RECURSIVE_WALK,
    CLAIM_NO_DUPLICATE_SOURCES,
    CLAIM_NO_UNBOUNDED_GROWTH,
    CLAIM_NO_FILESYSTEM_IO,
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_VISUAL_CHANGE,
)

__all__ = [
    "ALLOWED_ROLES",
    "CLAIM_NO_DUPLICATE_SOURCES",
    "CLAIM_NO_FILESYSTEM_IO",
    "CLAIM_NO_IMPLICIT_DISCOVERY",
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_RECURSIVE_WALK",
    "CLAIM_NO_SYMLINK_FOLLOW",
    "CLAIM_NO_UNBOUNDED_GROWTH",
    "CLAIM_NO_VISUAL_CHANGE",
    "FIXED_CLAIMS",
    "MAX_ENTRIES_PER_SOURCE",
    "MAX_PATH_CHARS",
    "MAX_SOURCES",
    "MAX_TOTAL_ENTRIES",
    "ROLE_EXPLICIT",
    "ROLE_XDG_DATA_DIRS",
    "ROLE_XDG_DATA_HOME",
    "EnumerationSourceError",
    "EnumerationSourceSnapshot",
    "SourceDescriptor",
    "describe_enumeration_sources",
]


class EnumerationSourceError(ValueError):
    """A source descriptor, bound or path was refused by the contract."""


@dataclass(frozen=True)
class SourceDescriptor:
    """One accepted enumeration source: an allowlisted role and explicit path."""

    role: str
    path: str
    max_entries: int


@dataclass(frozen=True)
class EnumerationSourceSnapshot:
    """Immutable, deterministic, bounded source set with diagnostics only."""

    sources: Tuple[SourceDescriptor, ...]
    max_total_entries: int
    claims: Tuple[str, ...]

    def to_paths(self):
        """Ordered ``(role, path, max_entries)`` projection for a consumer."""
        return tuple(
            (source.role, source.path, source.max_entries)
            for source in self.sources
        )

    def to_dict(self):
        """Count/claim diagnostics; no role, path or caller text is echoed."""
        return {
            "source_count": len(self.sources),
            "max_total_entries": self.max_total_entries,
            "per_source_max_entries": tuple(
                source.max_entries for source in self.sources),
            "claims": list(self.claims),
        }


def _check_bound(value, name, ceiling):
    if type(value) is not int or not 1 <= value <= ceiling:
        raise EnumerationSourceError("invalid %s" % name)


def _checked_path(path, max_path_chars):
    if type(path) is not str or not path or len(path) > max_path_chars:
        raise EnumerationSourceError("invalid source path")
    if any(ord(char) < 0x20 or ord(char) == 0x7f
           or unicodedata.category(char) in _UNSAFE_UNICODE_CATEGORIES
           for char in path):
        raise EnumerationSourceError("source path contains an unsafe scalar")
    # Accept either platform's absolute-path grammar: a rooted POSIX path and
    # a drive-qualified Windows path are both explicit source locations. This
    # check is textual only; no component is resolved or stat'ed.
    if not (posixpath.isabs(path) or ntpath.isabs(path)):
        raise EnumerationSourceError("source path must be absolute")
    # Reject traversal components textually. No component is resolved and no
    # symlink is inspected: this contract never touches the filesystem.
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    if any(part == ".." for part in parts):
        raise EnumerationSourceError("source path contains a traversal component")
    return path


def _descriptor_value(descriptor, key):
    try:
        return descriptor[key]
    except Exception:
        # A caller-supplied Mapping may raise any exception from __getitem__
        # (a hostile implementation is not limited to KeyError/TypeError).
        # An unreadable descriptor is always a refusal, never a raw leak.
        raise EnumerationSourceError("source descriptor is unreadable") from None


def _checked_descriptor(descriptor, max_path_chars, max_entries_per_source):
    if not isinstance(descriptor, Mapping):
        raise EnumerationSourceError("source descriptor must be a mapping")
    try:
        keys = tuple(descriptor.keys())
    except Exception:
        # keys() and the iteration behind KeysView are caller code too; any
        # exception there is an unreadable descriptor, never a raw leak.
        raise EnumerationSourceError("source descriptor keys are unreadable") from None
    if not keys or any(type(key) is not str for key in keys):
        raise EnumerationSourceError("invalid source descriptor key")
    if len(keys) != len(set(keys)) or not set(keys).issubset(_DESCRIPTOR_KEYS):
        raise EnumerationSourceError("unknown or duplicated source descriptor key")
    if "role" not in keys or "path" not in keys:
        raise EnumerationSourceError("source descriptor is incomplete")

    role = _descriptor_value(descriptor, "role")
    if type(role) is not str or role not in ALLOWED_ROLES:
        raise EnumerationSourceError("unsupported enumeration source role")
    path = _checked_path(_descriptor_value(descriptor, "path"), max_path_chars)
    if "max_entries" in keys:
        entries = _descriptor_value(descriptor, "max_entries")
        _check_bound(entries, "per-source entry bound", max_entries_per_source)
    else:
        entries = max_entries_per_source
    return SourceDescriptor(role=role, path=path, max_entries=entries)


def describe_enumeration_sources(
    sources,
    *,
    max_sources=MAX_SOURCES,
    max_total_entries=MAX_TOTAL_ENTRIES,
    max_path_chars=MAX_PATH_CHARS,
    max_entries_per_source=MAX_ENTRIES_PER_SOURCE,
):
    """Return one bounded snapshot of caller-supplied enumeration sources.

    ``sources`` is a finite ordered sequence of descriptor mappings with the
    keys ``role`` and ``path`` and an optional ``max_entries``. Unordered
    containers and scalar/byte inputs are refused. Sources are emitted in
    fixed role-then-path order, so the result is independent of input order
    and hash seed. Duplicate ``(role, path)`` pairs are refused, and the sum
    of per-source caps must not exceed ``max_total_entries``.
    """
    _check_bound(max_sources, "source count bound", MAX_SOURCES)
    _check_bound(max_total_entries, "total entry bound", MAX_TOTAL_ENTRIES)
    _check_bound(max_path_chars, "path character bound", MAX_PATH_CHARS)
    _check_bound(max_entries_per_source, "per-source entry bound",
                 MAX_ENTRIES_PER_SOURCE)
    if not isinstance(sources, Sequence) or isinstance(
            sources, (str, bytes, bytearray, Mapping)):
        raise EnumerationSourceError("sources must be an ordered sequence")

    accepted = []
    seen = set()
    total = 0
    for descriptor in sources:
        if len(accepted) >= max_sources:
            raise EnumerationSourceError("too many enumeration sources")
        source = _checked_descriptor(
            descriptor, max_path_chars, max_entries_per_source)
        identity = (source.role, source.path)
        if identity in seen:
            raise EnumerationSourceError("duplicate enumeration source")
        seen.add(identity)
        total += source.max_entries
        if total > max_total_entries:
            raise EnumerationSourceError("source caps exceed total entry bound")
        accepted.append(source)

    accepted.sort(key=lambda source: (ALLOWED_ROLES.index(source.role),
                                      source.path))
    return EnumerationSourceSnapshot(
        sources=tuple(accepted),
        max_total_entries=max_total_entries,
        claims=FIXED_CLAIMS,
    )
