"""Offline validation of user-level XDG target paths.

Pure checks only: no writes, no root, no global/system locations. An
unprivileged per-user installer calls :func:`validate` (or the convenience
builders) before it touches the filesystem.

The XDG data-home resolver and the root-refusal policy are reused from the
existing ``tools.register_classic_preview`` installer rather than duplicated.
"""
import os
from collections.abc import Mapping
from pathlib import Path

from tools import register_classic_preview as _menu


class UnsafeXdgPath(ValueError):
    """Raised when a target is not a safe user-level XDG path."""


# XDG Base Directory spec: env var -> path relative to home when unset.
_BASES = {
    "data": ("XDG_DATA_HOME", (".local", "share")),
    "config": ("XDG_CONFIG_HOME", (".config",)),
    "cache": ("XDG_CACHE_HOME", (".cache",)),
    "state": ("XDG_STATE_HOME", (".local", "state")),
}


def _refuse_root():
    # Reuse the installer's existing root policy so the two cannot drift.
    try:
        _menu._unprivileged()
    except _menu.RegistrationError as exc:
        raise UnsafeXdgPath(str(exc)) from None


def _path_text(value, message):
    """Return the string form of a path-shaped caller value, or fail closed.

    ``pathlib.Path`` raises a bare ``TypeError`` for ints, containers, bytes
    and for a ``__fspath__`` that returns a non-str.  Every path-shaped input
    of this module is documented to raise :class:`UnsafeXdgPath` instead, so
    gate the conversion once here and reuse it at every entry point.
    """
    if not isinstance(value, (str, os.PathLike)):
        raise UnsafeXdgPath(message)
    try:
        text = os.fspath(value)
    except (TypeError, ValueError):
        raise UnsafeXdgPath(message) from None
    if not isinstance(text, str):
        raise UnsafeXdgPath(message)
    if "\x00" in text:
        raise UnsafeXdgPath("path contains a null byte")
    return text


def _home(home):
    if home is None:
        h = Path.home()
    else:
        h = Path(_path_text(home, "home must be a path"))
    if not h.is_absolute():
        raise UnsafeXdgPath("home must be absolute")
    return Path(os.path.normpath(str(h)))


def _is_within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def base_dir(kind, *, home=None, env=None):
    """Return the XDG base directory for *kind* (data/config/cache/state).

    Resolution is lexical: no directory is created and no symlink is followed.
    """
    # Guard the type before the dict lookup: an unhashable kind (list/dict)
    # would otherwise raise TypeError from the membership test instead of the
    # documented UnsafeXdgPath. The isinstance check short-circuits it.
    if not isinstance(kind, str) or kind not in _BASES:
        raise UnsafeXdgPath("unknown XDG base kind: " + str(kind))
    variable, default = _BASES[kind]
    if kind == "data" and home is None and env is None:
        # Delegate the real-environment data path to the existing installer.
        try:
            return Path(_menu.data_home())
        except _menu.RegistrationError as exc:
            raise UnsafeXdgPath(str(exc)) from None
    h = _home(home)
    environ = os.environ if env is None else env
    if not isinstance(environ, Mapping):
        raise UnsafeXdgPath("env must be a mapping")
    try:
        chosen = environ.get(variable)
    except (TypeError, ValueError, KeyError):
        raise UnsafeXdgPath("env must be a mapping") from None
    if chosen is not None:
        # Gate the *type* before the truth test: a hostile falsy value (False,
        # 0, []) must not be silently treated as "unset" and fall back to the
        # default base. Path(chosen) otherwise leaks built-in TypeError.
        text = _path_text(chosen, variable + " must be a path")
    else:
        text = ""
    if text:
        candidate = Path(text)
        if not candidate.is_absolute():
            raise UnsafeXdgPath(variable + " must be absolute")
    else:
        candidate = h.joinpath(*default)
    return Path(os.path.normpath(str(candidate)))


def _absolute(target):
    # Only str / os.PathLike are path-shaped. Reject everything else (int,
    # bool, list, dict, float, None, bytes, ...) with the documented domain
    # error before pathlib raises a bare TypeError. Also fail closed for a
    # PathLike whose __fspath__ is broken or returns non-str.
    text = _path_text(target, "target must be a path")
    p = Path(text)
    if not p.is_absolute():
        raise UnsafeXdgPath("target must be absolute")
    return p


def _has_symlink_component(path, root):
    """True if an existing component below *root* on the way to *path* is a link."""
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
        if not current.exists():
            break  # Later components cannot exist, so cannot be links.
    return False


def validate(target, *, home=None, env=None):
    """Validate an absolute *target* as a safe user-level XDG path.

    Return the normalized absolute :class:`~pathlib.Path`, or raise
    :class:`UnsafeXdgPath`. The function never writes to the filesystem.
    Containment under the user's home is what rules out global/system paths.
    """
    _refuse_root()
    h = _home(home)
    normalized = Path(os.path.normpath(str(_absolute(target))))
    if not _is_within(normalized, h):
        # normpath collapses '.' and '..', so this also catches traversal
        # that climbs above home and any path outside the user's own tree.
        raise UnsafeXdgPath("target escapes user home (traversal or global path)")
    if normalized != h and _has_symlink_component(normalized, h):
        raise UnsafeXdgPath("target path contains a symlink")
    return normalized


def target(kind, relative, *, home=None, env=None):
    """Build and validate a user-level XDG target from a *relative* subpath."""
    p = Path(_path_text(relative, "relative subpath must be a path"))
    if p.is_absolute():
        raise UnsafeXdgPath("relative subpath must not be absolute")
    if ".." in p.parts:
        raise UnsafeXdgPath("relative subpath must not contain '..'")
    candidate = base_dir(kind, home=home, env=env).joinpath(*p.parts)
    return validate(candidate, home=home, env=env)
