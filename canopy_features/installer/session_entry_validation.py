"""Offline validation of user-level XDG session entry metadata.

A session entry is a small ``.desktop`` file a display manager may read to
offer a login session (for example Canopy Classic). This module validates such
metadata before an installer writes or registers it. It never installs a file,
registers a session, starts a session, replaces a login manager, or executes
the entry's ``Exec`` command. It only stats the referenced binary.

Safety properties (fail closed):
- bounded file size and bounded directory scan (no unbounded memory);
- ``Exec`` must be one absolute path with no shell syntax, arguments or field
  codes, and its binary must exist as a regular non-symlink executable file;
- symlinked entry files, unknown keys and unknown groups are rejected.

Scope note: ``tools/register_classic_preview.py`` already writes a reversible
per-user *application menu* entry and permits quoted paths plus flags. That
launcher writer is reused as-is and not duplicated here. Session entries are a
different artifact: the display manager consumes ``~/.local/share/xsessions``
or ``wayland-sessions`` files, where an ``Exec`` is a fixed session binary.
This module therefore validates that narrow, stricter shape.

A validated entry is NOT proof of a working desktop, a trusted package, or a
successful login. Integration into the compiled Qt application is separate.
"""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import FrozenSet, Optional, Tuple

MAX_ENTRY_BYTES = 16_384
MAX_ENTRIES = 32
MAX_NAME_CHARS = 80
MAX_COMMENT_CHARS = 240
MAX_ICON_CHARS = 120

ALLOWED_TYPES = frozenset({"Application", "Session"})
REQUIRED_KEYS = frozenset({"Type", "Name", "Exec"})
OPTIONAL_KEYS = frozenset({"Comment", "Icon"})
ALLOWED_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# Allow only characters safe in a single fixed executable path. Whitespace,
# shell metacharacters, field codes (%) and expansion tokens are excluded.
_SAFE_EXEC_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "._-+@/\\:"
)


class SessionEntryError(ValueError):
    """Untrusted or unsupported session entry metadata."""


@dataclass(frozen=True)
class SessionEntry:
    """Validated metadata only; NOT an execution approval or login guarantee."""

    name: str
    exec_path: Path
    comment: str = ""
    icon: str = ""


@dataclass(frozen=True)
class ScanProblem:
    location: str
    reason: str


@dataclass(frozen=True)
class SessionEntryScan:
    entries: Tuple[SessionEntry, ...]
    problems: Tuple[ScanProblem, ...]
    checked_files: int


def _clean_string(value, label, maximum):
    if (not value or len(value) > maximum
            or value != value.strip() or _CONTROL.search(value)):
        raise SessionEntryError(
            f"{label} must be a clean string, max {maximum} characters"
        )
    return value


def _safe_exec_path(value):
    """Reject anything other than one absolute, shell-free executable path."""
    if not isinstance(value, str) or not value or _CONTROL.search(value):
        raise SessionEntryError("Exec must be a clean single-token path")
    if any(char not in _SAFE_EXEC_CHARS for char in value):
        raise SessionEntryError("Exec contains shell-unsafe characters")
    path = Path(value)
    if not path.is_absolute():
        raise SessionEntryError("Exec must be an absolute path")
    if ".." in path.parts:
        raise SessionEntryError("Exec path cannot contain '..'")
    return path


def _check_binary(path):
    """Stat the binary only; never launch it or inspect its contents."""
    if not path.is_file():
        raise SessionEntryError("session binary is missing")
    if path.is_symlink():
        raise SessionEntryError("session binary cannot be a symlink")
    if not os.access(str(path), os.X_OK):
        raise SessionEntryError("session binary is not executable")


def _parse(text):
    fields = {}
    in_entry = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_entry = stripped == "[Desktop Entry]"
            if not in_entry:
                raise SessionEntryError(f"unsupported group: {stripped}")
            continue
        if not in_entry:
            continue
        if "=" not in stripped:
            raise SessionEntryError("malformed session entry line")
        key, value = stripped.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in fields:
            raise SessionEntryError(f"duplicate key: {key}")
        fields[key] = value

    missing = REQUIRED_KEYS - fields.keys()
    if missing:
        raise SessionEntryError(f"missing required key(s): {sorted(missing)}")
    unknown = fields.keys() - ALLOWED_KEYS
    if unknown:
        raise SessionEntryError(f"unsupported key(s): {sorted(unknown)}")
    if fields["Type"] not in ALLOWED_TYPES:
        raise SessionEntryError("unsupported session entry Type")
    return fields


def validate_session_entry(entry_path):
    """Validate one untrusted session entry file. Never executes its Exec."""
    entry_path = Path(entry_path)
    if entry_path.is_symlink() or not entry_path.is_file():
        raise SessionEntryError("session entry must be a regular local file")
    with entry_path.open("rb") as handle:
        raw = handle.read(MAX_ENTRY_BYTES + 1)
    if len(raw) > MAX_ENTRY_BYTES:
        raise SessionEntryError("session entry exceeds 16 KiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SessionEntryError("session entry is not valid UTF-8") from exc

    fields = _parse(text)
    name = _clean_string(fields["Name"], "Name", MAX_NAME_CHARS)
    comment = _clean_string(fields["Comment"], "Comment", MAX_COMMENT_CHARS) \
        if "Comment" in fields else ""
    icon = _clean_string(fields["Icon"], "Icon", MAX_ICON_CHARS) \
        if "Icon" in fields else ""
    exec_path = _safe_exec_path(fields["Exec"])
    _check_binary(exec_path)
    return SessionEntry(name=name, exec_path=exec_path,
                        comment=comment, icon=icon)


def scan_session_entries(directory):
    """Validate at most 32 ``*.desktop`` entries in one user-level directory.

    Invalid entries are reported and excluded without stopping healthy ones.
    This is metadata inspection only; no entry is installed or executed.
    """
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise SessionEntryError("session entry directory must be a real directory")
    candidates = sorted(
        (item for item in root.iterdir()
         if item.suffix == ".desktop" and not item.is_dir()),
        key=lambda item: item.name,
    )
    if len(candidates) > MAX_ENTRIES:
        raise SessionEntryError("session entry directory exceeds 32 files")

    entries, problems = [], []
    for candidate in candidates:
        try:
            entries.append(validate_session_entry(candidate))
        except (SessionEntryError, OSError) as exc:
            problems.append(ScanProblem(candidate.name, str(exc)))
    return SessionEntryScan(
        entries=tuple(entries),
        problems=tuple(problems),
        checked_files=len(candidates),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entry", type=Path, help="user-level session entry file")
    args = parser.parse_args(argv)
    try:
        result = validate_session_entry(args.entry)
    except (SessionEntryError, OSError) as exc:
        print(f"SESSION_ENTRY_FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"SESSION_ENTRY_PASS: {result.name} "
          "(metadata only; no session started or login manager changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
