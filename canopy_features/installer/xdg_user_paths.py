"""Offline validation of user-level XDG target paths.

Pure checks only: no writes, no root, no global/system locations. An
unprivileged per-user installer calls :func:`validate` (or the convenience
builders) before it touches the filesystem.

The XDG data-home resolver and the root-refusal policy are reused from the
existing ``tools.register_classic_preview`` installer rather than duplicated.
"""
import os
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


def _home(home):
    h = Path(home) if home is not None else Path.home()
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
    if kind not in _BASES:
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
    chosen = environ.get(variable)
    if chosen:
        candidate = Path(chosen)
        if not candidate.is_absolute():
            raise UnsafeXdgPath(variable + " must be absolute")
    else:
        candidate = h.joinpath(*default)
    return Path(os.path.normpath(str(candidate)))


def _absolute(target):
    if target is None or isinstance(target, bytes):
        raise UnsafeXdgPath("target must be a path")
    text = str(target)
    if "\x00" in text:
        raise UnsafeXdgPath("target contains a null byte")
    p = Path(target)
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
    p = Path(relative)
    if p.is_absolute():
        raise UnsafeXdgPath("relative subpath must not be absolute")
    if ".." in p.parts:
        raise UnsafeXdgPath("relative subpath must not contain '..'")
    candidate = base_dir(kind, home=home, env=env).joinpath(*p.parts)
    return validate(candidate, home=home, env=env)
