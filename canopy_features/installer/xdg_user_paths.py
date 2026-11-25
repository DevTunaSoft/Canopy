"""Validate user-level XDG target paths without root or global changes.

Offline, read-only policy helper for installers. It resolves XDG user base
directories from the environment with safe per-user defaults, then checks that
a relative install target stays under its base. It refuses root, absolute
targets, path traversal, symlinked path components and oversized paths.

This module performs no writes, starts no services and changes no session.
It is a policy check only: a passing result does not install anything or prove
a working desktop until an installer consumes the returned path.
"""

import os
from pathlib import Path

__all__ = [
    "UnsafeUserPathError",
    "XDG_USER_VARS",
    "MAX_PATH_CHARS",
    "refuse_root",
    "user_base",
    "ensure_user_level",
    "validate_target",
    "validate_user_target",
]


class UnsafeUserPathError(ValueError):
    """Raised when a target is not a safe user-level XDG location."""


# XDG user variable -> default directory under the user's home directory.
XDG_USER_VARS = {
    "XDG_DATA_HOME": ".local/share",
    "XDG_CONFIG_HOME": ".config",
    "XDG_CACHE_HOME": ".cache",
    "XDG_STATE_HOME": ".local/state",
}

# Plain defensive bound; keeps validation work and memory bounded.
MAX_PATH_CHARS = 4096


def _has_symlink_component(path):
    """Return True if any existing component of path is a symbolic link.

    Walks components without following the final link, so an alias cannot
    hide a redirect to a global location.
    """
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def refuse_root():
    """Refuse validation that could lead to root or system-wide changes."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise UnsafeUserPathError("root operation refused")


def user_base(name, *, home=None, env=None):
    """Return the absolute base directory for an XDG user variable.

    Uses the environment value when set; otherwise the per-user default under
    home. A relative environment value is always rejected.
    """
    if name not in XDG_USER_VARS:
        raise UnsafeUserPathError("unsupported XDG variable")
    environ = os.environ if env is None else env
    root = Path(home) if home is not None else Path.home()
    chosen = environ.get(name)
    if chosen:
        base = Path(chosen)
    else:
        base = root.joinpath(*XDG_USER_VARS[name].split("/"))
    if not base.is_absolute():
        raise UnsafeUserPathError(name + " must be absolute")
    return base


def ensure_user_level(base, home):
    """Return base normalized, refusing a base outside the user's home."""
    base = Path(os.path.normpath(str(Path(base))))
    home = Path(os.path.normpath(str(Path(home))))
    try:
        base.relative_to(home)
    except ValueError:
        raise UnsafeUserPathError(
            "XDG base lies outside user home (global path refused)"
        )
    return base


def validate_target(base, relative):
    """Validate a relative install target under an absolute XDG base.

    Returns the normalized absolute target path. Raises UnsafeUserPathError
    for a non-absolute base, an absolute target, path traversal, a symlinked
    component, or an oversized path.
    """
    base = Path(base)
    if not base.is_absolute():
        raise UnsafeUserPathError("XDG base must be absolute")
    relative = Path(relative)
    if relative.is_absolute():
        raise UnsafeUserPathError("target must be relative to the XDG base")

    candidate = base / relative
    if len(str(candidate)) > MAX_PATH_CHARS:
        raise UnsafeUserPathError("target path too long")

    # Lexical normalization exposes traversal without following any symlink.
    normalized = Path(os.path.normpath(str(candidate)))
    try:
        normalized.relative_to(os.path.normpath(str(base)))
    except ValueError:
        raise UnsafeUserPathError("target escapes XDG base (path traversal)")

    if _has_symlink_component(normalized):
        raise UnsafeUserPathError("target contains a symlink component")
    return normalized


def validate_user_target(name, relative, *, home=None, env=None):
    """Resolve an XDG user base and validate a relative target beneath it."""
    refuse_root()
    root = Path(home) if home is not None else Path.home()
    base = ensure_user_level(user_base(name, home=root, env=env), root)
    return validate_target(base, relative)
