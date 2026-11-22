"""Apply freedesktop desktop-entry visibility semantics (offline, stdlib only).

This is a small, modular decision component. It answers one question: should a
.desktop entry be shown in a launcher or application menu? It does not launch
apps, read the desktop database, watch files or start any service.

Semantics follow the Desktop Entry Specification (recognized keys ``Hidden``,
``NoDisplay``, ``OnlyShowIn``, ``NotShowIn``) and match GLib's
``g_app_info_should_show`` / ``g_desktop_app_info_get_show_in``:

* ``Hidden=true`` or ``NoDisplay=true`` hides the entry. These win over any
  desktop matching (conflicting flags are resolved here, never guessed).
* Desktop names are case-sensitive and ``XDG_CURRENT_DESKTOP`` is a
  colon-separated list considered in order. The first match decides: a match
  in ``OnlyShowIn`` shows the entry, a match in ``NotShowIn`` hides it. When a
  name appears in both, ``OnlyShowIn`` takes precedence (spec/GLib behavior).
* Default is visible, except when ``OnlyShowIn`` is present: then the default
  is hidden. An empty ``OnlyShowIn=`` therefore hides the entry everywhere.
* An unknown desktop (no value, empty value, or no match) falls back to that
  default. A missing or malformed boolean is false, matching GLib.

``TryExec`` and MIME/default-app handling are intentionally out of scope.
This component is not wired into the compiled Qt application; integrating it
with the launcher would be separate work and is not proven by these helpers.
"""
import os


# Bound memory when reading an untrusted .desktop file.
_MAX_BYTES = 1 << 20

# Desktop Entry booleans are "true"/"false" (case-insensitive). A few common
# truthy tokens are accepted; anything else (including missing) is false.
_TRUE = frozenset(("1", "true", "yes", "on"))


def parse_desktop_entry(text):
    """Return the ``[Desktop Entry]`` keys of *text* as a case-sensitive dict.

    Comments, other groups (such as ``[Desktop Action ...]``) and malformed
    lines are ignored. Values are kept as raw strings for the caller.
    """
    fields = {}
    group = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1].strip()
            continue
        if group != "Desktop Entry" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def read_desktop_entry(path):
    """Parse a single .desktop file, replacing bad bytes and capping the read."""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return parse_desktop_entry(handle.read(_MAX_BYTES))


def _as_bool(value):
    return isinstance(value, str) and value.strip().lower() in _TRUE


def _as_list(value):
    """Return a semicolon list, or None when the key is absent."""
    if value is None:
        return None
    return [item.strip() for item in value.split(";") if item.strip()]


def _as_desktops(current_desktops):
    if current_desktops is None:
        current_desktops = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if isinstance(current_desktops, str):
        current_desktops = current_desktops.split(":")
    names = []
    for name in current_desktops:
        name = str(name).strip()
        if name:
            names.append(name)
    return names


def should_show(fields, current_desktops=None):
    """Return True when the entry described by *fields* should be visible.

    *fields* is a mapping of desktop-entry key to raw string value, normally
    from :func:`parse_desktop_entry`. *current_desktops* may be a colon string,
    an iterable of names, or None to read ``XDG_CURRENT_DESKTOP``.
    """
    if _as_bool(fields.get("Hidden")) or _as_bool(fields.get("NoDisplay")):
        return False

    only = _as_list(fields.get("OnlyShowIn"))
    not_in = _as_list(fields.get("NotShowIn"))

    for desktop in _as_desktops(current_desktops):
        if only is not None and desktop in only:
            return True
        if not_in is not None and desktop in not_in:
            return False
    return only is None


def should_show_file(path, current_desktops=None):
    """Visibility decision for a .desktop file on disk."""
    return should_show(read_desktop_entry(path), current_desktops)
