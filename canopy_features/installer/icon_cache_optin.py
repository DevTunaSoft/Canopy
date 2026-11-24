"""Describe an optional icon-cache refresh for user-owned theme directories.

This is an installer *description* helper only. It never executes a cache
tool, never changes a cache file, never installs packages and never uses an
administrator account. A caller gets a frozen description it may display or
turn into text; running anything remains an explicit user decision.
"""
from dataclasses import dataclass
import re
import shlex
import shutil
from pathlib import PurePosixPath


CACHE_TOOL = "gtk-update-icon-cache"
MAX_THEME_DIRS = 16
MAX_PATH_CHARS = 512
MAX_TOOL_CHARS = 256
PRIVILEGED_TOKEN = re.compile(r"(?i)(?:^|[^a-z])(?:sudo|pkexec|doas|runuser|su)(?:[^a-z]|$)")
SYSTEM_HOME_ROOTS = frozenset({
    "usr", "etc", "var", "opt", "bin", "sbin", "lib", "lib64",
    "boot", "proc", "sys", "dev", "run", "snap",
})


class IconCacheDescriptionError(ValueError):
    """Invalid, unsafe or ambiguous description request."""


class PrivilegedRefreshRefused(IconCacheDescriptionError):
    """Caller asked for an administrator action; none is ever described."""


@dataclass(frozen=True)
class RefreshDescription:
    """Bounded, immutable result that an installer may show to the user."""

    available: bool
    tool: str
    reason: str
    directories: tuple
    commands: tuple

    @property
    def text(self):
        """Plain text for an installer label; no command is executed."""
        lines = [
            "Optional icon cache refresh (user-owned theme directories only).",
            "Canopy does not run this command and does not use administrator privileges.",
        ]
        if self.available:
            lines.append("If you want a refresh, run these commands yourself:")
            lines.extend(self.commands)
        else:
            lines.append(
                "Not described: " + self.tool + " was not found. "
                "Canopy does not install packages or refresh system caches."
            )
        return "\n".join(lines)

    def as_dict(self):
        """Plain JSON-ready snapshot; mutating it cannot alter this object."""
        return {
            "available": self.available,
            "tool": self.tool,
            "reason": self.reason,
            "directories": list(self.directories),
            "commands": list(self.commands),
            "text": self.text,
        }


def _clean_text(value, label, maximum):
    if type(value) is not str or not value or len(value) > maximum:
        raise IconCacheDescriptionError("invalid " + label)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise IconCacheDescriptionError("control character in " + label)
    return value


def _home_path(home):
    if isinstance(home, PurePosixPath):
        home = str(home)
    text = _clean_text(home, "home directory", MAX_PATH_CHARS)
    path = PurePosixPath(text)
    # A single-part absolute path is a root, not a user home: '/' is caught
    # below, while the POSIX double-slash root ('//') has parts ('//',) and
    # must not reach the parts[1] lookup (it raised IndexError). Fail closed.
    if (not path.is_absolute() or path == PurePosixPath("/")
            or len(path.parts) < 2 or ".." in path.parts):
        raise IconCacheDescriptionError("home must be an absolute user directory")
    if path.parts[1] in SYSTEM_HOME_ROOTS:
        raise IconCacheDescriptionError("home must not be a system directory")
    return path


def _theme_dirs(home, icon_dirs):
    if icon_dirs is None or isinstance(icon_dirs, (str, bytes)):
        raise IconCacheDescriptionError("icon directories must be an iterable of paths")
    try:
        iterator = iter(icon_dirs)
    except TypeError as exc:
        raise IconCacheDescriptionError("icon directories must be iterable") from exc

    # Read one item past the cap so a hostile/endless iterable cannot grow memory.
    from itertools import islice
    items = tuple(islice(iterator, MAX_THEME_DIRS + 1))
    if not items or len(items) > MAX_THEME_DIRS:
        raise IconCacheDescriptionError("icon directory count out of bounds")

    result = []
    for item in items:
        if not isinstance(item, (str, PurePosixPath)):
            raise IconCacheDescriptionError("icon directory must be a POSIX path")
        text = _clean_text(str(item), "icon directory", MAX_PATH_CHARS)
        path = PurePosixPath(text)
        if not path.is_absolute() or ".." in path.parts:
            raise IconCacheDescriptionError("icon directory must be a normalized absolute path")
        if path == home or home not in path.parents:
            raise IconCacheDescriptionError("icon directory must be inside the home directory")
        result.append(str(path))
    return tuple(dict.fromkeys(result))


def _cache_tool(tool_lookup):
    candidate = tool_lookup(CACHE_TOOL)
    if candidate is None:
        return None
    if type(candidate) is not str:
        raise IconCacheDescriptionError("cache tool lookup must return a path")
    text = _clean_text(candidate, "cache tool", MAX_TOOL_CHARS)
    if PRIVILEGED_TOKEN.search(text):
        raise PrivilegedRefreshRefused("privileged cache tool refused")
    return text


def describe_refresh(home, icon_dirs, *, tool_lookup=shutil.which, assume_root=False):
    """Describe, never perform, an optional user-scoped icon-cache refresh.

    ``tool_lookup`` is injectable for offline tests. ``assume_root`` exists so
    a caller request for administrator scope is refused explicitly, not
    silently translated into a command.
    """
    if type(assume_root) is not bool:
        raise IconCacheDescriptionError("assume_root must be a boolean")
    if assume_root:
        raise PrivilegedRefreshRefused("forced root action is not supported")

    home_path = _home_path(home)
    directories = _theme_dirs(home_path, icon_dirs)
    tool = _cache_tool(tool_lookup)
    if tool is None:
        return RefreshDescription(False, CACHE_TOOL, "TOOL_MISSING", directories, ())
    commands = tuple(
        tool + " " + shlex.quote(directory) for directory in directories
    )
    return RefreshDescription(True, CACHE_TOOL, "TOOL_AVAILABLE", directories, commands)
