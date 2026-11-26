"""Bounded, read-only producer for the Classic launcher's native catalog.

The host owns one XDG data home. This module reads only the explicit
``<data home>/applications`` directory it is given, parses each regular
``*.desktop`` file through the existing desktop-entry parser, and feeds the
existing launcher catalog ingest contract. It emits the exact headerless
bridge format consumed by ``LauncherCatalogModel``:
``app_id<TAB>title<LF>`` rows, UTF-8, deterministic order, no other bytes.

No implicit host path is scanned, no symlink is followed, no recursive walk
occurs, and there is no network, process, timer, cache or privileged write.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from canopy_features.apps.launch_argv import DESKTOP_ID
from canopy_features.launcher.desktop_entry_parser import (
    DEFAULT_MAX_BYTES,
    DesktopEntryError,
    parse,
)
from canopy_features.launcher.launcher_catalog_ingest import (
    MAX_ENTRIES,
    CatalogIngestError,
    compose_launcher_catalog,
)

APPLICATIONS_DIR_NAME = "applications"
MAX_DIRECTORY_ENTRIES = 512
MAX_FILENAME_CHARS = 256
MAX_SNAPSHOT_BYTES = 64 * 1024

__all__ = [
    "APPLICATIONS_DIR_NAME",
    "MAX_DIRECTORY_ENTRIES",
    "MAX_FILENAME_CHARS",
    "MAX_SNAPSHOT_BYTES",
    "NativeCatalogError",
    "produce_catalog_bytes",
]


class NativeCatalogError(ValueError):
    """A source path, directory or desktop entry was refused."""


def _check_limit(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise NativeCatalogError("invalid producer bound")


def _checked_path(applications_dir):
    if isinstance(applications_dir, (str, os.PathLike)) and not isinstance(
            applications_dir, bytes):
        try:
            path = Path(applications_dir)
        except (TypeError, ValueError, OSError):
            raise NativeCatalogError("invalid applications directory") from None
    else:
        raise NativeCatalogError("invalid applications directory")
    if not path.is_absolute() or path.name != APPLICATIONS_DIR_NAME:
        raise NativeCatalogError("applications directory must be an absolute XDG path")
    text = str(path)
    if any(ord(char) < 0x20 or ord(char) == 0x7f for char in text):
        raise NativeCatalogError("invalid applications directory")
    return path


def _lstat(path):
    try:
        return os.lstat(path)
    except OSError:
        raise NativeCatalogError("applications source is unavailable") from None


def _reject_symlink_components(path):
    """No component of the explicit root may be a symlink or a non-directory."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        info = _lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise NativeCatalogError("symlinked source path is refused")
        if not stat.S_ISDIR(info.st_mode):
            raise NativeCatalogError("applications source is not a directory")


def _read_entry(path, max_file_bytes):
    """One bounded read of one already-proven regular file; no writes."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    fd = None
    try:
        fd = os.open(path, flags | nofollow)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise NativeCatalogError("desktop entry is not a regular file")
        data = os.read(fd, max_file_bytes + 1)
    except NativeCatalogError:
        raise
    except OSError:
        raise NativeCatalogError("desktop entry is unreadable") from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    if len(data) > max_file_bytes:
        raise NativeCatalogError("desktop entry exceeds size bound")
    return data


def produce_catalog_bytes(
    applications_dir,
    *,
    max_entries=MAX_ENTRIES,
    max_file_bytes=DEFAULT_MAX_BYTES,
    max_directory_entries=MAX_DIRECTORY_ENTRIES,
    max_snapshot_bytes=MAX_SNAPSHOT_BYTES,
):
    """Return one deterministic, bounded TSV snapshot as UTF-8 bytes.

    Every refusal is fail-closed: no partial snapshot is returned and no
    source file is modified. Only the explicitly supplied directory is read.
    """
    _check_limit(max_entries, 1, MAX_ENTRIES)
    _check_limit(max_file_bytes, 1, DEFAULT_MAX_BYTES)
    _check_limit(max_directory_entries, 1, MAX_DIRECTORY_ENTRIES)
    _check_limit(max_snapshot_bytes, 1, MAX_SNAPSHOT_BYTES)

    root = _checked_path(applications_dir)
    _reject_symlink_components(root)
    if not stat.S_ISDIR(_lstat(root).st_mode):
        raise NativeCatalogError("applications source is not a directory")

    # Count while scanning: a hostile directory must never be fully
    # materialized just to discover that it is too large. Keep at most the
    # allowed number of names and refuse on the first entry beyond it.
    names = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if len(names) >= max_directory_entries:
                    raise NativeCatalogError(
                        "applications directory exceeds entry bound")
                names.append(entry.name)
    except OSError:
        raise NativeCatalogError("applications directory is unreadable") from None

    sources = []
    for name in names:
        if type(name) is not str or not name or len(name) > MAX_FILENAME_CHARS:
            raise NativeCatalogError("invalid directory entry name")
        if any(ord(char) < 0x20 or ord(char) == 0x7f for char in name):
            raise NativeCatalogError("invalid directory entry name")
        if DESKTOP_ID.fullmatch(name) is None:
            continue
        path = root / name
        info = _lstat(path)
        if not stat.S_ISREG(info.st_mode):
            # lstat on a symlink reports S_IFLNK, so this refuses a link
            # without following it. The O_NOFOLLOW read below closes the
            # replacement window on hosts that support that flag.
            raise NativeCatalogError("symlinked or non-regular entry refused")
        sources.append((name, path))

    parsed = []
    for name, path in sources:
        data = _read_entry(path, max_file_bytes)
        try:
            record = parse(data, max_bytes=max_file_bytes,
                           require_application=True)
        except DesktopEntryError:
            raise NativeCatalogError("desktop entry refused") from None
        parsed.append((name, record))

    try:
        snapshot = compose_launcher_catalog(parsed, max_entries=max_entries)
    except CatalogIngestError:
        raise NativeCatalogError("catalog ingest refused a source") from None
    if not snapshot.rows:
        raise NativeCatalogError("catalog snapshot is empty")

    lines = ["%s\t%s\n" % (row.app_id, row.title)
             for row in sorted(snapshot.rows, key=lambda row: row.app_id)]
    wire = "".join(lines).encode("utf-8")
    if len(wire) > max_snapshot_bytes:
        raise NativeCatalogError("catalog snapshot exceeds byte bound")
    return wire
