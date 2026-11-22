"""Detect X11/Wayland runtime capability hints from environment only.

Read-only and side-effect free: never opens a display socket, runs a command,
starts or stops a compositor, or changes any setting. A valid display
variable is a hint, not proof of a connected or controllable session.
"""

import os
import re

SCHEMA_VERSION = 1
BACKEND_X11 = "x11"
BACKEND_WAYLAND = "wayland"
BACKEND_HEADLESS = "headless"

MAX_VALUE_LEN = 256
MAX_NOTES = 8

_X11_DISPLAY = re.compile(
    r"^(?P<host>[A-Za-z0-9_.\[\]/:\-]*):(?P<display>\d{1,5})"
    r"(?:\.(?P<screen>\d{1,5}))?$"
)
# libwayland names its runtime socket wayland-N; accept that bounded form or
# an absolute path. Arbitrary bare names are rejected as capability hints.
_WL_SOCKET = re.compile(r"^wayland-[A-Za-z0-9_.\-]{1,127}$")


def _present(env, key):
    """True when a key exists with a non-None value."""
    return key in env and env.get(key) is not None


def _text(env, key):
    """Return a bounded, printable single-line value or an empty string."""
    value = env.get(key)
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > MAX_VALUE_LEN:
        return ""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return ""
    return value


def valid_x11_display(value):
    """True for :N, :N.M, host:N or host:N.M display specifications."""
    return (isinstance(value, str) and 0 < len(value) <= MAX_VALUE_LEN
            and bool(_X11_DISPLAY.match(value)))


def valid_wayland_display(value):
    """True for a bounded socket name or a safe absolute socket path."""
    if not isinstance(value, str) or not value or len(value) > MAX_VALUE_LEN:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return False
    if value.startswith("/"):
        return ".." not in value.split("/")
    return bool(_WL_SOCKET.match(value))


def detect(env=None):
    """Return a JSON-serializable capability report for the given environment.

    env defaults to os.environ. Pure: no I/O and no process or compositor
    control. Callers decide what the reported hints mean for their session.
    """
    if env is None:
        env = os.environ
    session = _text(env, "XDG_SESSION_TYPE").lower()[:32]
    if session not in ("x11", "wayland", "tty", "unspecified"):
        session = session or "unknown"

    x11_raw = _text(env, "DISPLAY")
    wl_raw = _text(env, "WAYLAND_DISPLAY")
    x11_ok = valid_x11_display(x11_raw)
    wl_ok = valid_wayland_display(wl_raw)

    invalid = []
    notes = []
    if _present(env, "DISPLAY") and not x11_ok:
        invalid.append("DISPLAY")
    if _present(env, "WAYLAND_DISPLAY") and not wl_ok:
        invalid.append("WAYLAND_DISPLAY")

    if session in ("x11", "wayland"):
        wanted_ok = wl_ok if session == "wayland" else x11_ok
        backend = session if wanted_ok else BACKEND_HEADLESS
        if not wanted_ok:
            key = "WAYLAND_DISPLAY" if session == "wayland" else "DISPLAY"
            notes.append("declared %s session lacks a valid %s" % (session, key))
    elif wl_ok or x11_ok:
        if wl_ok and x11_ok:
            notes.append("both display variables valid without a declared session type")
        backend = BACKEND_WAYLAND if wl_ok else BACKEND_X11
        notes.append("backend inferred from display variables, not compositor state")
    else:
        backend = BACKEND_HEADLESS
        if session in ("tty", "unspecified"):
            notes.append("no graphical display variables in a non-graphical session")
        elif not x11_raw and not wl_raw:
            notes.append("no graphical display variables present")

    return {
        "schema_version": SCHEMA_VERSION,
        "probe_only": True,
        "backend": backend,
        "headless": backend == BACKEND_HEADLESS,
        "session_type": session,
        "x11_hint": x11_ok,
        "wayland_hint": wl_ok,
        "x11_display": x11_raw if x11_ok else None,
        "wayland_display": wl_raw if wl_ok else None,
        "invalid_display_vars": invalid,
        "notes": notes[:MAX_NOTES],
    }
