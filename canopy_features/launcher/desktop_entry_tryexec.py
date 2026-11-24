"""Offline evaluation of freedesktop Desktop Entry ``TryExec`` availability.

``TryExec`` is an install probe: a path used only to decide whether an
application is present. This module checks the filesystem alone. It never
starts a process, opens a shell, polls, keeps state, or walks without a bound.
Bare names are resolved against an explicit PATH (or the process PATH) with
``shutil.which``; absolute paths are checked directly.
"""
from __future__ import annotations

import os
import shutil
import stat
from typing import Any, Mapping

__all__ = ["is_tryexec_available", "tryexec_available_for_entry"]


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
    candidate = tryexec.strip()
    if not candidate:
        return True
    if "\x00" in candidate or "%" in candidate:
        return False
    # shutil.which() raises a raw TypeError from os.fspath for a non-string
    # path. Enforce this module's search_path: str | None contract here so a
    # caller always gets a controlled, named error. Values that need no probe
    # still short-circuit above and ignore search_path.
    if search_path is not None and not isinstance(search_path, str):
        raise TypeError("search_path must be a string or None")
    resolved = shutil.which(candidate, path=search_path)
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
