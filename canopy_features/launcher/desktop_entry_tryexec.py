"""Offline evaluation of freedesktop Desktop Entry ``TryExec`` availability.

``TryExec`` is an install probe: a path used only to decide whether an
application is present. This module checks the filesystem alone. It never
starts a process, opens a shell, polls, keeps state, or walks without a bound.
Bare names are resolved against an explicit PATH (or the process PATH) with
``shutil.which``; absolute paths are checked directly. An explicit PATH never
picks up the current directory, and a relative path-looking TryExec value
cannot bypass that PATH.
"""
from __future__ import annotations

import os
import shutil
import stat
from typing import Any, Mapping

__all__ = ["is_tryexec_available", "tryexec_available_for_entry"]


def _is_absolute_path(value: str) -> bool:
    """Reject drive-relative and root-only paths as well as plain relative ones."""
    if not os.path.isabs(value):
        return False
    if os.name == "nt":
        drive, _ = os.path.splitdrive(value)
        # "\\tool" is absolute on Windows only because it inherits the
        # current drive, which an explicit search path must not supply.
        return bool(drive)
    return True


def _resolve_in_explicit_path(candidate: str, search_path: str) -> str | None:
    """Resolve a bare name using only the caller's PATH entries.

    ``shutil.which`` prepends the current directory to an explicit PATH on
    Windows, and PATH may contain an empty (cwd) entry on either platform.
    Search each entry separately and accept a hit only when it really lives
    under that entry, so cwd files cannot answer an isolated probe.
    """
    for entry in search_path.split(os.pathsep):
        if not entry:
            continue
        # Joining first gives which() a directory component, so it cannot
        # inject "." ahead of the explicit entry on Windows.
        resolved = shutil.which(os.path.join(entry, candidate))
        if resolved is None:
            continue
        base = os.path.abspath(entry)
        try:
            if os.path.commonpath((base, os.path.abspath(resolved))) == base:
                return resolved
        except ValueError:
            # Different Windows drives have no common path.
            continue
    return None


def is_tryexec_available(
    tryexec: str | None,
    *,
    search_path: str | None = None,
) -> bool:
    """Return whether a ``TryExec`` value passes its install probe.

    ``None`` or an empty value imposes no probe and returns ``True``. Any
    other value must resolve to an existing regular file that is executable.
    Field codes and NUL bytes are refused. The named binary is never run.

    ``search_path`` uses the same format as ``PATH``; ``None`` means the
    current process ``PATH``. Passing it explicitly keeps evaluation offline
    and deterministic.
    """
    if tryexec is None:
        return True
    if not isinstance(tryexec, str):
        raise TypeError("TryExec must be a string or None")
    # Fail closed on the *raw* value before any whitespace folding. str.strip()
    # treats C0 separators (0x1c-0x1f) as whitespace, so checking only the
    # stripped candidate would launder a control-wrapped path into a clean name
    # and return a false launchable verdict. Non-printable characters (C0/C1
    # controls, bidi overrides, zero-width text) must never name an executable,
    # even when a matching file exists.
    if any(not char.isprintable() for char in tryexec):
        return False
    candidate = tryexec.strip()
    if not candidate:
        return True
    if "%" in candidate:
        return False
    # shutil.which() raises a raw TypeError from os.fspath for a non-string
    # path. Enforce this module's search_path: str | None contract here so a
    # caller always gets a controlled, named error. Values that need no probe
    # still short-circuit above and ignore search_path.
    if search_path is not None and not isinstance(search_path, str):
        raise TypeError("search_path must be a string or None")
    # A value with a directory component is a path, not a command name. Only
    # a truly absolute path may bypass search_path; drive-relative and
    # "./tool" values would otherwise consult the current directory.
    drive, _ = os.path.splitdrive(candidate)
    if (os.path.dirname(candidate) or drive) and not _is_absolute_path(candidate):
        return False
    resolved = (
        _resolve_in_explicit_path(candidate, search_path)
        if search_path is not None and not os.path.dirname(candidate)
        else shutil.which(candidate, path=search_path)
    )
    if resolved is None:
        return False
    try:
        info = os.stat(resolved)
    except OSError:
        return False
    # shutil.which accepts FIFOs and devices; TryExec must name a real file.
    if not stat.S_ISREG(info.st_mode):
        return False
    return os.access(resolved, os.X_OK)


def tryexec_available_for_entry(
    entry: Any,
    *,
    search_path: str | None = None,
) -> bool:
    """Evaluate ``TryExec`` from a parsed Desktop Entry's values mapping.

    Accepts the parser's ``DesktopEntry`` object or a plain mapping. The
    parser is not imported, so this module stays independent and unit-tests
    without Qt, GIO or a Linux session.
    """
    values = entry if isinstance(entry, Mapping) else getattr(entry, "values", None)
    if not isinstance(values, Mapping):
        raise TypeError("entry must expose a values mapping")
    return is_tryexec_available(values.get("TryExec", ""), search_path=search_path)
