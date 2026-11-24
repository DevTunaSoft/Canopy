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


def _as_path(value, label):
    """Return a str path argument, or fail closed with PathJailError.

    ``os.fspath`` already rejects non-path scalars and containers, but accepts
    ``bytes``; ``pathlib.Path`` then raises a raw ``TypeError`` that callers
    catching the module's domain error cannot contain. Reject bytes here so
    every wrong-typed argument reaches callers as PathJailError.
    """
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise PathJailError(f"invalid {label}: {value!r}") from exc
    if isinstance(raw, bytes):
        raise PathJailError(f"invalid {label} type: {value!r}")
    return raw


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
    character whose lowercase form is not itself a single code point, or whose
    lowercase does not round-trip under ``str.upper()`` (compatibility letters
    such as ``ẞ``/``ß``, ``K``/``k`` and ``Å``/``å`` are distinct NTFS names).

    On Windows the OS invariant case table (used by ``ntpath.normcase``) is
    authoritative for NTFS identity; use it so no compatibility letter can be
    folded into a distinct name. Elsewhere there is no host table for the
    Windows convention, so keep the conservative Unicode fold below.
    """
    if os.name == "nt":
        return os.path.normcase(component)
    folded = []
    for char in component:
        lowered = char.lower()
        if len(lowered) != 1:
            # Full folding would expand (ß -> ss); NTFS does not expand.
            folded.append(char)
            continue
        # Only fold a *stable* cased character: one whose lowercase maps back
        # to itself under str.upper(). Windows/NTFS case tables do not equate
        # compatibility letters with their plain counterparts even though
        # str.lower() does (ẞ->ß but ß.upper()==SS, K->k but k.upper()==K,
        # Å->å but å.upper()==Å). Treating those pairs as equal would make a
        # directory outside the jail root appear contained -- a fail-open.
        # Keeping any non-round-tripping character verbatim can only make the
        # comparison stricter, never widen the jail.
        if lowered.upper() != char:
            folded.append(char)
            continue
        folded.append(lowered)
    return "".join(folded)


def canonicalize(path, *, must_exist=False):
    """Return an absolute canonical :class:`~pathlib.Path`.

    Symlinks and ``..`` segments are resolved. ``must_exist`` requires the
    final component to exist (open-style checks). NUL bytes, symlink loops
    and permission failures become :class:`PathJailError`.
    """
    raw = _as_path(path, "path")
    # Windows pathlib silently truncates at NUL; reject it at the boundary.
    if "\x00" in raw:
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
    cand_parts = tuple(Path(_as_path(candidate, "candidate")).parts)
    root_parts = tuple(Path(_as_path(root, "root")).parts)
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

    if candidate is None:
        candidate_path = root_path
    else:
        raw = _as_path(candidate, "candidate")
        if raw.strip() == "":
            candidate_path = root_path
        else:
            candidate_path = Path(raw)
            if not candidate_path.is_absolute():
                candidate_path = root_path / candidate_path

    candidate_real = canonicalize(candidate_path, must_exist=must_exist)
    if not is_contained(candidate_real, root_path, case_sensitive=case_sensitive):
        raise PathJailError(f"path escapes allowed root: {candidate!r}")
    return candidate_real
