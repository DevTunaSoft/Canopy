"""Resolve freedesktop icon-theme names without replacing locked artwork.

This is a small, offline, host-side component. It reads an ``Icon=`` value
from a desktop entry or launcher model and returns one bounded decision:

* ``RESOLVED`` -- a normal theme icon file was found.
* ``LOCKED``   -- the name belongs to an approval-locked asset; the frozen
  path is returned and no theme candidate is ever consulted.
* ``MISSING``  -- no candidate exists anywhere in the theme search chain.
* ``REJECTED`` -- the value or a candidate failed a safety check (path
  escape, symlink, cyclic inheritance, oversized file, bad input).

Design constraints (deliberate, not incidental):

* No network, no subprocess, no timer, no background service, no polling.
* All filesystem work is lazy and bounded: at most ``max_themes`` themes,
  ``MAX_INDEX_BYTES`` for each ``index.theme`` and ``MAX_ICON_BYTES`` for
  each icon file.
* Themes are parsed from ``index.theme`` but never written to.
* Every returned path is checked for containment inside its search root,
  so a ``..`` segment or an escaping symlink fails closed.
* A name listed in ``locked`` short-circuits theme lookup. This is the
  "do not silently replace locked assets" guarantee: a system theme that
  happens to ship ``Files.png`` can never displace the approved master.

This module is a pure resolver. It does not load QML, call GIO, prove a
working desktop, or grant visual approval. Wiring it into the compiled Qt
launcher remains a separate, future integration task.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, replace
import os
from pathlib import Path
import re
from typing import Dict, Mapping, Optional, Sequence, Tuple

__all__ = [
    "DEFAULT_THEME",
    "MAX_ICON_BYTES",
    "MAX_INDEX_BYTES",
    "MAX_THEMES",
    "SUPPORTED_EXTENSIONS",
    "IconThemeResolver",
    "Resolution",
    "resolve_icon_name",
]

DEFAULT_THEME = "hicolor"
SUPPORTED_EXTENSIONS = (".png", ".svg", ".xpm")
MAX_INDEX_BYTES = 1024 * 1024
MAX_ICON_BYTES = 8 * 1024 * 1024
MAX_THEMES = 32

# A theme or icon name is a single safe path component. The leading
# character must be alphanumeric, so ".", ".." and hidden names cannot
# pass. Separators, backslashes and drive letters are rejected outright.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")

RESOLVED = "RESOLVED"
LOCKED = "LOCKED"
MISSING = "MISSING"
REJECTED = "REJECTED"


@dataclass(frozen=True)
class Resolution:
    """One bounded decision for a single icon value."""

    status: str
    icon: str
    path: Optional[Path] = None
    theme: Optional[str] = None
    reason: str = ""
    searched: Tuple[str, ...] = ()


@dataclass(frozen=True)
class _Theme:
    name: str
    roots: Tuple[Path, ...]
    inherits: Tuple[str, ...]
    directories: Tuple[str, ...]


def _as_path(value) -> Optional[Path]:
    """Accept str/Path only; never coerce arbitrary objects to a path."""
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    return None


def _contained(root: Path, candidate: Path) -> bool:
    """True when candidate resolves inside root (no escape, no symlink)."""
    try:
        root_real = root.resolve(strict=False)
        candidate_real = candidate.resolve(strict=False)
        candidate_real.relative_to(root_real)
    except (OSError, ValueError):
        return False
    return True


def _safe_regular_file(path: Path, base: Path, limit: int) -> bool:
    """Fail-closed checks shared by index files, icons and locked assets."""
    if not path.is_absolute() or path.is_symlink():
        return False
    if not _contained(base, path):
        return False
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return False
    except OSError:
        return False
    return True


class IconThemeResolver:
    """Offline freedesktop icon-theme name resolver with locked-asset guard.

    Args:
        data_home: user data root (``$XDG_DATA_HOME``); theme dirs live under
            ``<data_home>/icons``. Use an explicit path in tests.
        data_dirs: system data roots (``$XDG_DATA_DIRS``). Defaults are only
            applied when ``use_environment`` is true.
        locked: mapping of icon name to the approved, frozen asset path.
            A locked name is never looked up in a theme.
        approved_root: optional containment root for locked assets.
        default_theme: theme searched first when ``resolve`` has no theme.
        extensions: deterministic search order; PNG wins by default.
        max_themes: cap on the inheritance/search chain length.
        use_environment: read ``XDG_DATA_HOME`` / ``XDG_DATA_DIRS`` when no
            explicit roots were supplied.
    """

    def __init__(self, *, data_home=None, data_dirs=None, locked=None,
                 approved_root=None, default_theme=DEFAULT_THEME,
                 extensions=SUPPORTED_EXTENSIONS, max_themes=MAX_THEMES,
                 use_environment=False):
        home = _as_path(data_home)
        if home is None and use_environment:
            candidate = os.environ.get("XDG_DATA_HOME")
            if candidate and Path(candidate).is_absolute():
                home = Path(candidate)

        dirs = data_dirs
        if dirs is None and use_environment:
            raw = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
            dirs = tuple(p for p in raw.split(":") if p)
        if dirs is None:
            dirs = ()
        data_dirs_tuple = tuple(
            p for p in (_as_path(d) for d in dirs)
            if p is not None and p.is_absolute()
        )

        self.data_home = home
        self.data_dirs = data_dirs_tuple
        self.approved_root = _as_path(approved_root)
        self.default_theme = default_theme
        self.extensions = tuple(extensions)
        self.max_themes = max(1, int(max_themes))

        normalised: Dict[str, Path] = {}
        for name, value in dict(locked or {}).items():
            path = _as_path(value)
            if not _NAME.fullmatch(name) or path is None:
                raise ValueError("invalid locked icon name or path")
            normalised[name] = path
        self.locked: Mapping[str, Path] = normalised

    # -- public API -----------------------------------------------------

    def resolve(self, icon_value, theme=None) -> Resolution:
        """Resolve one ``Icon=`` value. Never raises for bad icon input."""
        text = icon_value if isinstance(icon_value, str) else ""
        if not text or "\x00" in text:
            return Resolution(REJECTED, text, reason="empty or invalid icon value")

        if self._is_absolute_value(text):
            return self._resolve_absolute(text)

        if not _NAME.fullmatch(text):
            return Resolution(
                REJECTED, text,
                reason="unsafe icon name: path separators or traversal refused")

        if text in self.locked:
            return self._resolve_locked(text)

        theme_name = theme or self.default_theme
        chain, error = self._inheritance_chain(theme_name)
        if error is not None:
            return Resolution(REJECTED, text, reason=error)

        searched = []
        for name in chain:
            current = self._load_theme(name)
            if current is None:
                continue
            searched.append(name)
            for root in current.roots:
                for sub in ("",) + current.directories:
                    directory = root / sub if sub else root
                    for extension in self.extensions:
                        candidate = directory / (text + extension)
                        decision = self._candidate(candidate, root, name, text)
                        if decision.status != MISSING:
                            return replace(decision, searched=tuple(searched))

        return Resolution(
            MISSING, text, reason="icon not found in theme chain",
            searched=tuple(searched))

    # -- input classification ------------------------------------------

    @staticmethod
    def _is_absolute_value(text: str) -> bool:
        return text.startswith(("/", "\\")) or bool(_DRIVE.match(text))

    def _resolve_absolute(self, text: str) -> Resolution:
        """An absolute Icon= path is allowed only inside known data roots."""
        path = Path(text)
        roots = ([self.data_home] if self.data_home is not None else []) + list(
            self.data_dirs)
        if not any(root is not None and _contained(root, path) for root in roots):
            return Resolution(
                REJECTED, text, reason="absolute icon path outside allowed roots")
        for root in roots:
            if root is None:
                continue
            if _safe_regular_file(path, root, MAX_ICON_BYTES):
                return Resolution(
                    RESOLVED, text, path=path, theme=None,
                    reason="absolute icon path inside data root")
        return Resolution(
            REJECTED, text, reason="absolute icon path is unsafe or unreadable")

    # -- locked assets --------------------------------------------------

    def _resolve_locked(self, name: str) -> Resolution:
        path = self.locked[name]
        base = self.approved_root or path.parent
        if not _safe_regular_file(path, base, MAX_ICON_BYTES):
            return Resolution(
                REJECTED, name,
                reason="locked asset missing, unsafe or outside approved root")
        return Resolution(
            LOCKED, name, path=path, theme=None,
            reason="locked asset retained; theme substitution refused")

    # -- theme discovery ------------------------------------------------

    def _theme_roots(self, name: str) -> Tuple[Path, ...]:
        bases: Sequence[Optional[Path]] = (
            ([self.data_home] if self.data_home is not None else []) +
            list(self.data_dirs))
        found = []
        for base in bases:
            if base is None:
                continue
            root = base / "icons" / name
            try:
                if root.is_symlink() or not _contained(base, root):
                    continue
                if root.is_dir():
                    found.append(root)
            except OSError:
                continue
        return tuple(found)

    def _load_theme(self, name: str) -> Optional[_Theme]:
        roots = self._theme_roots(name)
        if not roots:
            return None
        for root in roots:
            index = root / "index.theme"
            if not _safe_regular_file(index, root, MAX_INDEX_BYTES):
                continue
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                with index.open("r", encoding="utf-8") as handle:
                    parser.read_file(handle)
                inherits = self._names(parser.get(
                    "Icon Theme", "Inherits", fallback=""))
                directories = self._directories(parser.get(
                    "Icon Theme", "Directories", fallback=""))
            except (OSError, UnicodeError, configparser.Error):
                # A malformed index fails closed; it is never guessed at.
                return None
            return _Theme(name, roots, inherits, directories)
        return None

    @staticmethod
    def _names(raw: str) -> Tuple[str, ...]:
        return tuple(
            item.strip() for item in raw.split(",")
            if _NAME.fullmatch(item.strip())
        )

    @staticmethod
    def _directories(raw: str) -> Tuple[str, ...]:
        directories = []
        for item in raw.split(","):
            parts = item.strip().split("/")
            if parts and all(_PART.fullmatch(part) for part in parts):
                directories.append("/".join(parts))
        return tuple(directories)

    def _inheritance_chain(self, start):
        """Depth-first theme chain with ancestor-cycle and size guards."""
        if not _NAME.fullmatch(start):
            return None, "invalid icon theme name"
        chain = []
        added = set()

        def visit(name, ancestors):
            # A back-edge to an ancestor is a real cycle. A shared parent
            # reached by two branches is not, and is visited only once.
            if name in ancestors:
                return "cyclic icon theme inheritance: " + name
            if name not in added and len(added) >= self.max_themes:
                return "too many icon themes in inheritance chain"
            if name not in added:
                added.add(name)
                chain.append(name)
            theme = self._load_theme(name)
            if theme is None:
                return None
            parents = list(theme.inherits)
            if name != DEFAULT_THEME:
                parents.append(DEFAULT_THEME)
            for parent in parents:
                error = visit(parent, ancestors + (name,))
                if error is not None:
                    return error
            return None

        error = visit(start, ())
        return (chain, None) if error is None else (None, error)

    # -- candidate validation ------------------------------------------

    def _candidate(self, path: Path, root: Path, theme: str,
                   name: str) -> Resolution:
        if not _contained(root, path):
            return Resolution(
                REJECTED, name, theme=theme, reason="icon candidate escapes theme root")
        if path.is_symlink():
            return Resolution(
                REJECTED, name, theme=theme, reason="symlink icon candidate refused")
        try:
            if not path.exists():
                return Resolution(MISSING, name, theme=theme)
            if not path.is_file():
                return Resolution(
                    REJECTED, name, theme=theme, reason="icon candidate is not a regular file")
            if path.stat().st_size > MAX_ICON_BYTES:
                return Resolution(
                    REJECTED, name, theme=theme, reason="icon candidate exceeds size cap")
        except OSError:
            return Resolution(
                REJECTED, name, theme=theme, reason="icon candidate unreadable")
        return Resolution(
            RESOLVED, name, path=path, theme=theme, reason="theme icon resolved")


def resolve_icon_name(icon_value, **kwargs) -> Resolution:
    """Convenience wrapper: build a resolver and resolve one icon value."""
    return IconThemeResolver(**kwargs).resolve(icon_value)
