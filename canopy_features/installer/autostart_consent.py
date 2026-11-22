"""Model opt-in-only session autostart registration (offline, per-user).

Policy/model component, not a system installer. It writes only inside a
caller-supplied root directory, so tests and a future installer share the same
decision logic without touching real user config, the Windows registry, a
login session, or a background service.

Modeled rules:
  * Opt-in only. Consent must be explicit GRANTED. DENIED or UNSET never
    activates autostart and writes nothing.
  * No duplicates. More than one entry for an application id, or a conflicting
    command, is refused instead of silently doubling autostart.
  * Reversible and owned. Each entry has a SHA-256 ownership record; removal
    deletes only an exact file this component created.

The generated .desktop payload follows the freedesktop autostart keys used by
Linux Mint (Hidden, X-GNOME-Autostart-enabled). On Windows hosts the same model
is used unchanged against a supplied directory; no registry or Startup-folder
write is performed here.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

GRANTED = "granted"
DENIED = "denied"
UNSET = "unset"
_CONSENT = frozenset((GRANTED, DENIED, UNSET))

SKIP_NO_CONSENT = "SKIP_NO_CONSENT"
WRITE = "WRITE"
NOOP = "NOOP"

NOT_REGISTERED = "NOT_REGISTERED"
REGISTERED = "REGISTERED"
DUPLICATE = "DUPLICATE"
MODIFIED_OR_UNOWNED = "MODIFIED_OR_UNOWNED"
UNSAFE = "UNSAFE"
UNREGISTERED = "UNREGISTERED"

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MAX_FILE = 8192
_MAX_MANIFEST = 8192


class ConsentError(ValueError):
    """Invalid consent, unsafe path, or unowned removal."""


class DuplicateEntryError(ConsentError):
    """Autostart entry present more than once or with a conflicting command."""


@dataclass(frozen=True)
class AutostartEntry:
    app_id: str
    command: str

    def __post_init__(self):
        if not isinstance(self.app_id, str) or not _ID.fullmatch(self.app_id):
            raise ConsentError("invalid application id")
        if (not isinstance(self.command, str) or not self.command
                or any(ch in self.command for ch in "\n\r\x00")):
            raise ConsentError("invalid Exec command")


def decide(consent, desired, existing=()):
    """Pure opt-in/duplicate policy.

    Return SKIP_NO_CONSENT, WRITE or NOOP. `existing` is an iterable of
    AutostartEntry already registered. Raise DuplicateEntryError for multiple
    entries or a command that conflicts with an existing one.
    """
    if consent not in _CONSENT:
        raise ConsentError("unknown consent state")
    if not isinstance(desired, AutostartEntry):
        raise ConsentError("desired must be an AutostartEntry")
    if consent != GRANTED:
        return SKIP_NO_CONSENT
    matches = [e for e in existing
               if e.app_id == desired.app_id or e.command == desired.command]
    if len(matches) > 1:
        raise DuplicateEntryError("multiple autostart entries for this application")
    if matches:
        if matches[0].app_id != desired.app_id or matches[0].command != desired.command:
            raise DuplicateEntryError("conflicting autostart entry")
        return NOOP
    return WRITE


def _paths(root):
    root = Path(root)
    return {
        "root": root,
        "autostart": root / "autostart",
        "manifest": root / "autostart" / ".canopy-ownership.json",
    }


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _check_folders(p):
    for key in ("root", "autostart"):
        path = p[key]
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ConsentError("unsafe registration directory")


def _manifest(p):
    f = p["manifest"]
    if f.is_symlink():
        return None
    if not f.exists():
        return {}
    if not f.is_file() or f.stat().st_size > _MAX_MANIFEST:
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if (not isinstance(data, dict)
            or any(not isinstance(k, str) or not _ID.fullmatch(k)
                   or not isinstance(v, str) or not _HASH.fullmatch(v)
                   for k, v in data.items())):
        return None
    return data


def _write_manifest(p, data):
    f = p["manifest"]
    tmp = f.with_name(f.name + ".tmp")
    payload = json.dumps(data, sort_keys=True).encode("utf-8")
    with tmp.open("wb") as handle:
        handle.write(payload)
    os.replace(tmp, f)
    f.chmod(0o600)


def _field(text, key):
    prefix = key + "="
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    return None


def _read_entries(p):
    folder = p["autostart"]
    entries = []
    if not folder.exists():
        return entries
    for f in sorted(folder.glob("*.desktop")):
        if f.is_symlink() or not f.is_file() or f.stat().st_size > _MAX_FILE:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        app_id = _field(text, "X-Canopy-App-Id") or f.stem
        command = _field(text, "Exec") or "<invalid-exec>"
        entries.append(AutostartEntry(app_id, command))
    return entries


def _payload(entry):
    return (
        "[Desktop Entry]\nType=Application\nVersion=1.0\n"
        "Name=Canopy\n"
        "Exec=" + entry.command + "\n"
        "Hidden=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-Canopy-App-Id=" + entry.app_id + "\n"
    ).encode("utf-8")


def register(root, entry, consent):
    """Register `entry` only when `consent` is GRANTED; refuse duplicates."""
    p = _paths(root)
    _check_folders(p)
    action = decide(consent, entry, _read_entries(p))
    if action != WRITE:
        return action
    folder = p["autostart"]
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    f = folder / (entry.app_id + ".desktop")
    if f.exists() or f.is_symlink():
        raise ConsentError("autostart path already exists; refusing overwrite")
    manifest = _manifest(p)
    if manifest is None:
        raise ConsentError("unsafe or unreadable ownership record")
    payload = _payload(entry)
    created = False
    try:
        with f.open("xb") as handle:
            created = True
            handle.write(payload)
        f.chmod(0o600)
        manifest[entry.app_id] = _sha(payload)
        _write_manifest(p, manifest)
    except (OSError, ValueError):
        if created:
            f.unlink(missing_ok=True)
        raise
    return WRITE


def status(root, app_id):
    """Return registration state for `app_id`, including DUPLICATE/UNSAFE."""
    if not isinstance(app_id, str) or not _ID.fullmatch(app_id):
        raise ConsentError("invalid application id")
    p = _paths(root)
    try:
        _check_folders(p)
    except ConsentError:
        return UNSAFE
    folder = p["autostart"]
    if folder.exists() and (folder.is_symlink() or not folder.is_dir()):
        return UNSAFE
    matches = []
    for f in (sorted(folder.glob("*.desktop")) if folder.exists() else ()):
        if f.is_symlink() or not f.is_file() or f.stat().st_size > _MAX_FILE:
            return UNSAFE
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return MODIFIED_OR_UNOWNED
        if _field(text, "X-Canopy-App-Id") == app_id:
            matches.append((f, text))
    if not matches:
        return NOT_REGISTERED
    if len(matches) > 1:
        return DUPLICATE
    f, text = matches[0]
    manifest = _manifest(p)
    if (manifest is None or manifest.get(app_id) != _sha(f.read_bytes())
            or _field(text, "Hidden") != "false"):
        return MODIFIED_OR_UNOWNED
    return REGISTERED


def unregister(root, app_id):
    """Remove only an exact, owned entry; refuse duplicate or modified files."""
    state = status(root, app_id)
    if state == DUPLICATE:
        raise DuplicateEntryError("duplicate entries; removed nothing")
    if state != REGISTERED:
        raise ConsentError("not exact-byte owned; removed nothing")
    p = _paths(root)
    f = p["autostart"] / (app_id + ".desktop")
    manifest = _manifest(p)
    if manifest is None or manifest.get(app_id) != _sha(f.read_bytes()):
        raise ConsentError("ownership changed during removal")
    f.unlink()
    del manifest[app_id]
    _write_manifest(p, manifest)
    return UNREGISTERED
