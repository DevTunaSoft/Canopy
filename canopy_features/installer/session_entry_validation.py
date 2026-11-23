"""Offline validator for user-level Canopy session-entry desktop metadata.

Reads one ``$XDG_DATA_HOME/{xsessions,wayland-sessions}/*.desktop`` entry and
checks its shape, its Exec/TryExec safety and the named session binary.
No writes, subprocesses, root, display/login-manager changes, polling, network
or background services. A VALID report is metadata evidence only: it does not
start a session, install a session, or prove Linux Mint desktop acceptance.
"""

import configparser
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Tuple

# Reuse the project's existing XDG data-home rule instead of redefining it.
from tools.register_classic_preview import data_home as _user_data_home


MAX_ENTRY_BYTES = 8192
MAX_VALUE_CHARS = 512
MAX_EXEC_CHARS = 512
MAX_EXEC_ARGS = 8
SESSION_DIRS = ("xsessions", "wayland-sessions")

# Session Exec must name a binary directly. Interpreters and wrappers are
# refused, matching the shell-free policy of tools/register_classic_preview.py
# and the deny cases in prototype/classic/main.cpp.
SHELL_OR_WRAPPER = frozenset({
    "sh", "bash", "dash", "zsh", "ksh", "fish", "env", "sudo", "pkexec",
    "xargs", "nohup", "systemd-run", "python", "python3", "perl", "ruby",
})
LOGIN_MANAGER = frozenset({
    "gdm", "gdm3", "lightdm", "sddm", "lxdm", "xdm", "kdm", "display-manager",
})
# Double quotes delimit a path with spaces; single quotes and shell expansion
# characters are never needed in a session entry and are refused outright.
_EXEC_BANNED = frozenset("\\'$`%;&|<>*?[]~{}")


@dataclass(frozen=True)
class ValidationReport:
    """Outcome plus the safe metadata extracted from the entry."""

    valid: bool
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    name: str
    exec_path: str
    session: str


def _result(errors, warnings=(), name="", exec_path="", session=""):
    return ValidationReport(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        name=name,
        exec_path=exec_path,
        session=session,
    )


def _control_chars(value):
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _exec_tokens(value, code):
    """Split a desktop Exec value without a shell; return bounded tokens."""
    if (not isinstance(value, str) or not value
            or len(value) > MAX_EXEC_CHARS or _control_chars(value)):
        raise ValueError(code + ": Exec must be a bounded, single-line string")
    tokens = []
    current = []
    quoted = False
    for ch in value:
        if ch == '"':
            quoted = not quoted
            continue
        if ch in _EXEC_BANNED:
            raise ValueError(code + ": unsupported character in Exec")
        if ch.isspace() and not quoted:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(ch)
    if quoted:
        raise ValueError(code + ": unmatched quote in Exec")
    if current:
        tokens.append("".join(current))
    if not tokens or len(tokens) > MAX_EXEC_ARGS or any(not token for token in tokens):
        raise ValueError(code + ": Exec must have one to eight simple arguments")
    return tokens


def _binary_path(tokens, code):
    """First Exec/TryExec token must be a direct, local, absolute binary."""
    path = Path(tokens[0])
    name = path.name.lower()
    if (not path.is_absolute() or ".." in path.parts
            or name in SHELL_OR_WRAPPER or name in LOGIN_MANAGER):
        raise ValueError(code + ": session binary must be a direct absolute path")
    return path


def _checked_text(section, key, required, errors):
    value = section.get(key)
    if value is None or not value.strip():
        if required:
            errors.append("MISSING_" + key.upper() + ": " + key + " is required")
        return ""
    if len(value) > MAX_VALUE_CHARS or _control_chars(value):
        errors.append("UNSAFE_METADATA: " + key + " is unbounded or has control characters")
        return ""
    return value.strip()


def validate_session_entry(path, *, data_home=None):
    """Validate one local user session entry; never execute or modify it."""
    home = _user_data_home() if data_home is None else Path(data_home)
    entry = Path(path)
    if not home.is_absolute() or not entry.is_absolute():
        return _result(["UNSAFE_ENTRY_PATH: data home and entry must be absolute"])
    if (entry.suffix != ".desktop" or entry.is_symlink()
            or not entry.is_file()):
        return _result(["UNSAFE_ENTRY_PATH: entry must be a real .desktop file"])
    real_parent = Path(os.path.realpath(str(entry))).parent
    allowed = tuple(Path(os.path.realpath(str(home / name))) for name in SESSION_DIRS)
    if real_parent not in allowed:
        return _result(["UNSAFE_ENTRY_PATH: entry is outside the user's session directories"])
    session = real_parent.name

    try:
        with entry.open("r", encoding="utf-8") as handle:
            payload = handle.read(MAX_ENTRY_BYTES + 1)
    except (OSError, UnicodeError):
        return _result(["UNREADABLE_ENTRY: cannot read the entry as UTF-8"], session=session)
    if len(payload) > MAX_ENTRY_BYTES:
        return _result(["ENTRY_TOO_LARGE: entry exceeds 8192 bytes"], session=session)

    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str  # Desktop Entry keys are case-sensitive.
    try:
        parser.read_string(payload)
    except (configparser.Error, ValueError):
        return _result(["MALFORMED_DESKTOP_ENTRY: invalid desktop entry syntax"], session=session)
    if not parser.has_section("Desktop Entry"):
        return _result(["MISSING_DESKTOP_ENTRY: [Desktop Entry] group is required"], session=session)
    section = parser["Desktop Entry"]

    errors = []
    warnings = []
    name = _checked_text(section, "Name", True, errors)
    _checked_text(section, "Comment", False, errors)
    exec_value = _checked_text(section, "Exec", True, errors)
    tryexec_value = _checked_text(section, "TryExec", False, errors)
    entry_type = section.get("Type")
    if entry_type != "Application":
        errors.append("UNSUPPORTED_SESSION_TYPE: Type must be Application")

    exec_path = ""
    if exec_value:
        try:
            tokens = _exec_tokens(exec_value, "UNSAFE_EXEC")
            binary = _binary_path(tokens, "UNSAFE_EXEC")
            exec_path = str(binary)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if not binary.exists():
                errors.append("MISSING_SESSION_BINARY: " + exec_path)
            elif not binary.is_file():
                errors.append("UNSAFE_SESSION_BINARY: Exec target is not a regular file")
            elif binary.is_symlink():
                warnings.append("SESSION_BINARY_SYMLINK: resolve and review the target manually")
            elif not os.access(str(binary), os.X_OK):
                errors.append("NOT_EXECUTABLE: session binary lacks execute permission")

    if tryexec_value:
        try:
            try_tokens = _exec_tokens(tryexec_value, "UNSAFE_TRYEXEC")
            if len(try_tokens) != 1:
                raise ValueError("UNSAFE_TRYEXEC: TryExec must name one binary")
            try_binary = _binary_path(try_tokens, "UNSAFE_TRYEXEC")
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if not try_binary.exists():
                errors.append("MISSING_TRYEXEC_BINARY: " + str(try_binary))

    return _result(errors, warnings, name, exec_path, session)
