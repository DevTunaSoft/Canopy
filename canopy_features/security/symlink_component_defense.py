"""Reject symlinked directory components before privileged actions.

Offline, dependency-free guard for local filesystem paths. On POSIX every
component is opened with ``O_NOFOLLOW | O_DIRECTORY`` relative to the previously
opened descriptor, so a component swapped for a symlink between check and use
is refused atomically. Callers should perform the privileged action relative
to that descriptor (``dir_fd=``) via :func:`verified_directory` to stay
race-free. Windows has no ``dir_fd``/``O_NOFOLLOW``; there the guard uses an
``lstat`` walk and is best-effort only.

This is a modular guard, not a desktop integration: nothing here proves a
working Classic Qt shell until a caller wires it into a privileged path.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat

__all__ = [
    "UnsafePathError",
    "find_symlink_component",
    "reject_symlink_components",
    "verified_directory",
]


class UnsafePathError(ValueError):
    """Raised when a path is not safe to use for a privileged action."""


_POSIX_FD = (
    os.name == "posix"
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
)


def _components(path):
    """Return (absolute string, pathlib parts) without following symlinks."""
    try:
        raw = os.fspath(path)
    except (TypeError, ValueError) as exc:
        # Wrong types and hostile __fspath__ implementations are unsafe
        # paths, never caller-visible built-in exceptions.
        raise UnsafePathError("path must be a non-empty string") from exc
    if not isinstance(raw, str) or not raw:
        raise UnsafePathError("path must be a non-empty string")
    if "\x00" in raw:
        raise UnsafePathError("path contains a NUL byte")
    if os.pardir in Path(raw).parts:
        # abspath collapses '..' lexically, which can hide a link; fail closed.
        raise UnsafePathError("'..' components are not allowed")
    # abspath is lexical: it normalises separators but never resolves links.
    absolute = os.path.abspath(raw)
    return absolute, Path(absolute).parts


def find_symlink_component(path):
    """Return the first symlink component name, or None (portable lstat walk)."""
    _, parts = _components(path)
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except OSError as exc:
            raise UnsafePathError("cannot inspect path component: " + part) from exc
        if stat.S_ISLNK(mode):
            return part
    return None


def _open_verified_fd(parts):
    """Open every component with O_NOFOLLOW|O_DIRECTORY; return the final fd."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = os.open(parts[0], flags)
    except OSError as exc:
        raise UnsafePathError("cannot open path root") from exc
    for part in parts[1:]:
        try:
            next_fd = os.open(part, flags, dir_fd=fd)
        except OSError as exc:
            os.close(fd)
            raise UnsafePathError("symlinked or unsafe path component: " + part) from exc
        os.close(fd)
        fd = next_fd
    return fd


@contextmanager
def verified_directory(path):
    """Yield (fd, Path) after rejecting every symlinked component.

    POSIX: fd is an open descriptor for the verified directory; use it with
    ``dir_fd`` for the privileged action. Windows: fd is None and the check is
    a best-effort lstat walk.
    """
    absolute, parts = _components(path)
    if _POSIX_FD:
        fd = _open_verified_fd(parts)
        try:
            yield fd, Path(absolute)
        finally:
            os.close(fd)
    else:
        link = find_symlink_component(absolute)
        if link is not None:
            raise UnsafePathError("symlinked path component: " + link)
        if not os.path.isdir(absolute):
            raise UnsafePathError("path is not an existing directory")
        yield None, Path(absolute)


def reject_symlink_components(path):
    """Return the absolute Path only if no component of path is a symlink.

    Raises UnsafePathError on symlinks, missing components, type changes,
    traversal components and unreadable paths. Bounded work: one descriptor at
    a time, one pass over the path; no polling, services or privileged calls.
    """
    with verified_directory(path) as (_, canonical):
        return canonical
