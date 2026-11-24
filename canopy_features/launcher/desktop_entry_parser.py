"""Offline parser for freedesktop Desktop Entry application metadata.

Reads one ``.desktop`` entry from bytes, validates UTF-8, and exposes the
fields a launcher needs. No process execution, shell, polling, background
service or filesystem walk. Exec quoting mirrors the writer convention in
``tools/register_classic_preview._quote``: tokens are never shell-evaluated.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from typing import Mapping

DEFAULT_MAX_BYTES = 64 * 1024

# Unicode "Other" and non-ASCII "Separator" categories. These characters can
# hide or re-order text when a launcher renders a Name/Comment/Icon, and C0
# separators are silently eaten by str.strip(). Zs (space) is deliberately not
# included so ordinary spacing and no-break spaces remain valid.
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def _has_nonprintable(text: str) -> bool:
    """True when *text* contains any control/format/noncharacter scalar."""
    return any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in text)


def _entry_lines(text: str):
    """Yield entry lines split on LF only, the Desktop Entry line ending.

    ``str.splitlines()`` also breaks on C0 separators (\x0b, \x0c,
    \x1c-\x1e), NEL (\x85) and Zl/Zp (\u2028/\u2029). Those scalars are in
    ``_UNSAFE_CATEGORIES`` but splitlines() consumes them before the per-line
    guard can see them, so a hostile line is silently rewritten into two
    clean-looking fields and a valid entry is claimed. Splitting on LF alone
    leaves them inside the raw line for the guard to reject. One trailing CR
    (CRLF) is dropped so files written on Windows keep parsing.
    """
    for raw in text.split("\n"):
        yield raw[:-1] if raw.endswith("\r") else raw


def _check_max_bytes(max_bytes: int) -> None:
    """Reject a non-positive or non-int byte limit before any read occurs."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise MalformedEntryError("invalid size limit")


def _byte_length(data) -> int:
    """Real byte length, including memoryviews with a non-byte element type.

    ``len(memoryview)`` counts elements, not bytes: a 200000-byte buffer viewed
    as 8-byte integers reports 25000. Enforcing ``max_bytes`` against that
    number lets an oversized entry through, so use ``nbytes`` for memoryviews.
    """
    if isinstance(data, memoryview):
        return data.nbytes
    return len(data)

_KEY = re.compile(r"[A-Za-z0-9-]+(?:\[[A-Za-z0-9_@.+:-]+\])?")
_GROUP = re.compile(r"[A-Za-z0-9][A-Za-z0-9 -]*")
_BOOLEANS = frozenset({"Terminal", "NoDisplay", "Hidden", "StartupNotify"})

__all__ = [
    "DEFAULT_MAX_BYTES",
    "DesktopEntry",
    "DesktopEntryError",
    "DuplicateKeyError",
    "InvalidEncodingError",
    "MalformedEntryError",
    "parse",
    "parse_file",
]


class DesktopEntryError(ValueError):
    """Base class for every refused input."""


class InvalidEncodingError(DesktopEntryError):
    """Input is not valid UTF-8."""


class MalformedEntryError(DesktopEntryError):
    """Input does not follow Desktop Entry structure."""


class DuplicateKeyError(DesktopEntryError):
    """A key occurs more than once in the main group."""


@dataclass(frozen=True)
class DesktopEntry:
    """Parsed ``[Desktop Entry]`` keys plus localized values."""

    values: Mapping[str, str]
    localized: Mapping[str, Mapping[str, str]]

    @property
    def type(self) -> str:
        return self.values.get("Type", "")

    @property
    def name(self) -> str:
        return self.values.get("Name", "")

    @property
    def exec(self) -> str:
        return self.values.get("Exec", "")

    @property
    def icon(self) -> str:
        return self.values.get("Icon", "")

    @property
    def terminal(self) -> bool:
        return self.values.get("Terminal", "false") == "true"

    @property
    def no_display(self) -> bool:
        return self.values.get("NoDisplay", "false") == "true"

    @property
    def hidden(self) -> bool:
        return self.values.get("Hidden", "false") == "true"

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(item for item in self.values.get("Categories", "").split(";") if item)

    def localized_name(self, locale: str) -> str:
        return self.localized.get("Name", {}).get(locale, "")

    def exec_argv(self) -> list[str]:
        """Split Exec by Desktop Entry quoting rules; no shell is involved.

        Field codes such as ``%f`` stay in the tokens for the caller to
        substitute after validating them.
        """
        tokens: list[str] = []
        current: list[str] = []
        quoted = False
        escaping = False
        started = False
        for char in self.exec:
            if escaping:
                current.append(char)
                escaping = False
                started = True
            elif char == "\\":
                escaping = True
                started = True
            elif char == '"':
                quoted = not quoted
                started = True
            elif not quoted and char.isspace():
                if started:
                    tokens.append("".join(current))
                    current = []
                    started = False
            else:
                current.append(char)
                started = True
        if quoted:
            raise MalformedEntryError("unterminated quote in Exec")
        if escaping:
            raise MalformedEntryError("dangling escape in Exec")
        if started:
            tokens.append("".join(current))
        return tokens


def parse(
    data: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    require_application: bool = True,
) -> DesktopEntry:
    """Parse one desktop entry, failing closed on malformed or ambiguous input."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("desktop entry data must be bytes")
    _check_max_bytes(max_bytes)
    if _byte_length(data) > max_bytes:
        raise MalformedEntryError("desktop entry exceeds size limit")
    try:
        text = bytes(data).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidEncodingError("desktop entry is not valid UTF-8") from exc

    values: dict[str, str] = {}
    localized: dict[str, dict[str, str]] = {}
    groups: set[str] = set()
    group: str | None = None
    continued = ""

    for raw in _entry_lines(text):
        line = continued + raw.strip()
        continued = ""
        if not line or line.startswith("#"):
            continue
        # Fail closed on the *raw* line, before strip() folds C0 separators
        # (0x1c-0x1f) into clean-looking text. The tryexec module already does
        # this for TryExec paths; the parser needs the same guard for the
        # display fields (Name, Icon, localized names, Comment, ...) it stores.
        if _has_nonprintable(raw):
            raise MalformedEntryError("non-printable character in entry")
        if line.endswith("\\"):
            continued = line[:-1]
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            if not _GROUP.fullmatch(name):
                raise MalformedEntryError("invalid group header")
            if name in groups:
                raise MalformedEntryError("duplicate group: " + name)
            groups.add(name)
            group = name
            continue
        if "=" not in line:
            raise MalformedEntryError("line without '='")
        if group is None:
            raise MalformedEntryError("key outside any group")
        key, value = (part.strip() for part in line.split("=", 1))
        if not _KEY.fullmatch(key):
            raise MalformedEntryError("invalid key: " + key)
        if group != "Desktop Entry":
            continue
        if key.endswith("]"):
            base, locale = key[:key.rfind("[")], key[key.rfind("[") + 1:-1]
            bucket = localized.setdefault(base, {})
            if locale in bucket:
                raise DuplicateKeyError("duplicate key: " + key)
            bucket[locale] = value
        else:
            if key in values:
                raise DuplicateKeyError("duplicate key: " + key)
            values[key] = value

    entry = DesktopEntry(values=values, localized=localized)
    if not entry.type:
        raise MalformedEntryError("missing Type")
    if require_application and entry.type != "Application":
        raise MalformedEntryError("Type must be Application")
    for key in ("Name", "Exec"):
        if not values.get(key):
            raise MalformedEntryError("missing " + key)
    for key in _BOOLEANS:
        if key in values and values[key] not in ("true", "false"):
            raise MalformedEntryError("invalid boolean: " + key)
    if not entry.exec_argv():
        raise MalformedEntryError("empty Exec")
    return entry


def parse_file(
    path: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    require_application: bool = True,
) -> DesktopEntry:
    """Parse a desktop entry file with a bounded read; never follow a walk."""
    _check_max_bytes(max_bytes)
    with Path(path).open("rb") as handle:
        data = handle.read(max_bytes + 1)
    return parse(data, max_bytes=max_bytes, require_application=require_application)
