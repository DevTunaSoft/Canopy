"""Stage escaped desktop launch entries with ownership records.

Offline, unprivileged staging only. This prepares a ``[Desktop Entry]`` file
and a SHA-256 ownership record inside a caller-owned staging directory.
Nothing is installed, registered, launched or polled here. Wiring the staged
entry into the compiled Qt application or a system installer remains
separate work.

The escaping and digest logic are reused from the project's existing
reversible menu registration tool rather than reimplemented.
"""
import json
import re
from pathlib import Path

from tools import register_classic_preview as menu

SCHEMA = 1
DEFAULT_ENTRY = "org.canopy.ClassicLaunch.desktop"
RECORD_NAME = "ownership.json"
# shortcut: one entry and one record per staging dir; add per-entry record names if multiple entries are needed.
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class StagingError(menu.RegistrationError):
    """Raised when an entry cannot be staged or verified safely."""


def quote_argument(value):
    """Escape one Exec argument using the project's desktop Exec quoter."""
    if not isinstance(value, str) or not value:
        raise StagingError("Exec arguments must be non-empty strings")
    try:
        return menu._quote(value)
    except menu.RegistrationError as exc:
        raise StagingError(str(exc)) from exc


def build_entry(name, exec_args, *, comment=None, icon=None):
    """Return UTF-8 bytes of a [Desktop Entry] with an escaped Exec field."""
    if (not isinstance(name, str) or not name
            or any(ch in name for ch in ("\n", "\r", "\x00", "="))):
        raise StagingError("invalid desktop entry name")
    args = list(exec_args)
    if not args:
        raise StagingError("Exec field requires at least one argument")
    command = " ".join(quote_argument(arg) for arg in args)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=" + name,
    ]
    if comment is not None:
        if any(ch in comment for ch in ("\n", "\r", "\x00")):
            raise StagingError("invalid desktop entry comment")
        lines.append("Comment=" + comment)
    lines.append("Exec=" + command)
    lines.append("Terminal=false")
    if icon is not None:
        if any(ch in icon for ch in ("\n", "\r", "\x00", "=")):
            raise StagingError("invalid desktop entry icon")
        lines.append("Icon=" + icon)
    lines.append("Categories=Utility;")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _safe_filename(name):
    return (isinstance(name, str) and name.endswith(".desktop")
            and "/" not in name and "\\" not in name
            and name not in (".", "..")
            and not any(ch in name for ch in ("\n", "\r", "\x00")))


def _payload(payload):
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise StagingError("payload must be non-empty bytes")
    if len(payload) > 8192:
        raise StagingError("payload exceeds staged entry size limit")
    return bytes(payload)


def stage(staging_dir, payload, *, filename=DEFAULT_ENTRY):
    """Write an entry and its ownership record, refusing to overwrite.

    Any file already at the entry or record path is treated as a user's file:
    staging fails and leaves it untouched.
    """
    folder = Path(staging_dir)
    data = _payload(payload)
    if not _safe_filename(filename):
        raise StagingError("invalid staged entry filename")
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise StagingError("staging directory is unsafe")
    entry = folder / filename
    record = folder / RECORD_NAME
    if entry.exists() or entry.is_symlink():
        raise StagingError("existing user entry: refusing to overwrite")
    if record.exists() or record.is_symlink():
        raise StagingError("existing ownership record: refusing to overwrite")
    marker = json.dumps(
        {"schema": SCHEMA, "entry": filename, "sha256": menu._sha(data)},
        sort_keys=True,
    ).encode("utf-8")
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    created = []
    try:
        for path, content, perms in ((entry, data, 0o644),
                                     (record, marker, 0o600)):
            with path.open("xb") as handle:
                created.append(path)
                handle.write(content)
            path.chmod(perms)
    except OSError:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return entry


def _read_record(record):
    if record.is_symlink() or not record.is_file() or record.stat().st_size > 4096:
        return None
    try:
        entry = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if (not isinstance(entry, dict)
            or set(entry) != {"schema", "entry", "sha256"}
            or type(entry["schema"]) is not int or entry["schema"] != SCHEMA
            or not isinstance(entry["entry"], str)
            or not isinstance(entry["sha256"], str)
            or not _HEX.fullmatch(entry["sha256"])):
        return None
    return entry


def verify(staging_dir, *, filename=DEFAULT_ENTRY):
    """Compare a staged entry against its ownership record.

    Returns OWNED, MODIFIED_OR_UNMANAGED, NOT_STAGED or UNSAFE.
    """
    folder = Path(staging_dir)
    entry = folder / filename
    record = folder / RECORD_NAME
    if folder.is_symlink() or entry.is_symlink() or record.is_symlink():
        return "UNSAFE"
    if not entry.exists() and not record.exists():
        return "NOT_STAGED"
    marker = _read_record(record)
    if marker is None or marker["entry"] != filename or not entry.is_file():
        return "MODIFIED_OR_UNMANAGED"
    if menu._sha(entry.read_bytes()) != marker["sha256"]:
        return "MODIFIED_OR_UNMANAGED"
    return "OWNED"
