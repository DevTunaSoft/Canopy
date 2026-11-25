"""Read-only Linux Mint release detection and compatibility classification.

Reads an os-release file from a caller-supplied path (default
``/etc/os-release``), reusing the project's existing safe ``parse_release``
helper rather than duplicating its validation. Reports Mint identity, a
strictly validated version, and a conservative compatibility value computed
against a caller-supplied support matrix.

Never writes files, runs processes, polls, or claims release acceptance.
"""
from pathlib import Path

from tools.mint_guest_preflight import MAX_RELEASE_BYTES, parse_release

DEFAULT_RELEASE_PATH = "/etc/os-release"
MINT_ID = "linuxmint"
MAX_VERSION_LEN = 16


def clean_version(value):
    """Return a strict dotted-numeric version or '' for forged/malformed data."""
    if not isinstance(value, str) or not value or len(value) > MAX_VERSION_LEN:
        return ""
    parts = value.split(".")
    if not 1 <= len(parts) <= 3:
        return ""
    if not all(part.isdigit() and len(part) <= 3 for part in parts):
        return ""
    return value


def read_release(path=DEFAULT_RELEASE_PATH):
    """Read a bounded os-release file. Return (fields, read_status)."""
    try:
        handle = Path(path).open("r", encoding="utf-8")
    except (OSError, ValueError):
        return {}, "missing-or-unreadable"
    try:
        with handle:
            # Read one byte past the cap so oversized files are detected
            # without loading them into memory.
            data = handle.read(MAX_RELEASE_BYTES + 1)
    except (OSError, UnicodeError):
        return {}, "unreadable"
    if len(data) > MAX_RELEASE_BYTES:
        return {}, "oversized"
    if not data.strip():
        return {}, "empty"
    return parse_release(data), "ok"


def detect(path=DEFAULT_RELEASE_PATH, supported=()):
    """Return a read-only Mint identity/compatibility report as a dict.

    ``supported`` is an iterable of version strings (for example ``("22",)``
    or ``("22.3",)``). A release matches on its full version or its major
    component. No value is treated as release acceptance.
    """
    fields, status = read_release(path)
    raw_id = fields.get("ID", "")
    is_mint = isinstance(raw_id, str) and raw_id.strip().lower() == MINT_ID
    version = clean_version(fields.get("VERSION_ID", "")) if is_mint else ""
    allowed = frozenset(str(item) for item in supported if str(item))

    if status != "ok":
        compatibility = "unknown"
    elif not is_mint:
        compatibility = "not_mint"
    elif not version:
        compatibility = "unknown"
    elif version in allowed or version.split(".")[0] in allowed:
        compatibility = "supported"
    else:
        compatibility = "unsupported"

    return {
        "source": str(path),
        "read_status": status,
        "mint_identified": is_mint,
        "version_id": version,
        "compatibility": compatibility,
        "probe_only": True,
        "release_acceptance": "NOT_RUN",
    }
