"""Canonical containment checks for user-selected filesystem paths.

Offline and synchronous. Filesystem access is limited to :mod:`pathlib`
resolution; there are no services, timers, polling, privileged calls or
network access. The safe entry point is :func:`resolve_within`: it canonicalizes
both the root and the candidate (resolving symlinks and ``..``) before a
component-wise containment check.

This mirrors the Classic Qt Files model contract, where navigation resolves
``canonicalFilePath()`` and requires it to stay under the canonical home path.
It does not prove that the compiled Qt application is wired to this module.
"""

import os
from pathlib import Path

__all__ = ["PathJailError", "canonicalize", "is_contained", "resolve_within"]


class PathJailError(ValueError):
    """Candidate path escapes its root or cannot be canonicalized."""


def _default_case_sensitive():
    # Match the Classic Qt model: Windows compares case-insensitively.
    return os.name != "nt"


def _fold_component(component):
    """Case-insensitive key for one path component, without expansion.

    NTFS and Qt compare names with *simple* (one-code-point-to-one-code-point)
    case folding. Python's ``str.casefold()`` is full Unicode folding and can
    expand a single character into several (``ß`` -> ``ss``, ``ﬀ`` -> ``ff``,
    ``ſ`` -> ``s``). Using it here would make two distinct NTFS directory
    names compare equal, so a path outside the jail root could be reported as
    contained -- a fail-open. Fold each code point independently and keep any
    character whose lowercase form is not itself a single code point.
    """
    folded = []
    for char in component:
        lowered = char.lower()
        folded.append(lowered if len(lowered) == 1 else char)
    return "".join(folded)


def canonicalize(path, *, must_exist=False):
    """Return an absolute canonical :class:`~pathlib.Path`.

    Symlinks and ``..`` segments are resolved. ``must_exist`` requires the
    final component to exist (open-style checks). NUL bytes, symlink loops
    and permission failures become :class:`PathJailError`.
    """
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise PathJailError(f"invalid path: {path!r}") from exc
    # Windows pathlib silently truncates at NUL; reject it at the boundary.
    nul = b"\x00" if isinstance(raw, bytes) else "\x00"
    if nul in raw:
        raise PathJailError(f"embedded NUL byte in path: {path!r}")
    try:
        return Path(raw).resolve(strict=must_exist)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathJailError(f"cannot canonicalize path: {path!r}") from exc


def is_contained(candidate, root, *, case_sensitive=None):
    """Return True when canonical ``candidate`` equals or lies under ``root``.

    Comparison is component-wise, so ``/home/u2`` is not treated as inside
    ``/home/u``. Expects canonical absolute paths; untrusted input must go
    through :func:`resolve_within` first. ``case_sensitive`` defaults to the
    host convention (False on Windows, True elsewhere) and can be set
    explicitly for cross-platform verification.
    """
    if case_sensitive is None:
        case_sensitive = _default_case_sensitive()
    cand_parts = tuple(Path(candidate).parts)
    root_parts = tuple(Path(root).parts)
    if not case_sensitive:
        cand_parts = tuple(_fold_component(part) for part in cand_parts)
        root_parts = tuple(_fold_component(part) for part in root_parts)
    return len(cand_parts) >= len(root_parts) and cand_parts[:len(root_parts)] == root_parts


def resolve_within(root, candidate, *, must_exist=False, case_sensitive=None):
    """Resolve user-selected ``candidate`` under ``root`` or raise PathJailError.

    ``root`` must be an existing directory. A relative ``candidate`` is taken
    relative to ``root``; an empty candidate means ``root`` itself. Absolute
    candidates, ``..`` traversal and symlinks are canonicalized first, so an
    escape is rejected even when the spelling starts with the root prefix.
    """
    root_path = canonicalize(root, must_exist=True)
    if not root_path.is_dir():
        raise PathJailError(f"root is not a directory: {root!r}")

    raw = "" if candidate is None else str(candidate)
    if raw.strip() == "":
        candidate_path = root_path
    else:
        candidate_path = Path(candidate)
        if not candidate_path.is_absolute():
            candidate_path = root_path / candidate_path

    candidate_real = canonicalize(candidate_path, must_exist=must_exist)
    if not is_contained(candidate_real, root_path, case_sensitive=case_sensitive):
        raise PathJailError(f"path escapes allowed root: {candidate!r}")
    return candidate_real
