"""Read-only probe for desktop app-launch capability.

Answers one narrow question: can this host resolve a desktop launch tool and
declare a usable graphical session? It never executes a probed tool, changes
settings, reads private environment values into its report, or starts a
background service. Complements ``tools/mint_guest_preflight.py`` (guest build
readiness) without duplicating its build or smoke checks.

This is a capability probe, not evidence of a working desktop, a real Mint
session, or a compiled Qt runtime test. Wiring it into the compiled Qt
application remains future integration work.
"""

import os
import shutil

SCHEMA_VERSION = 1

# Fixed allowlist only. No user-supplied or environment-supplied names.
LAUNCH_TOOLS = ("gio", "gtk-launch", "xdg-open")
SUPPORTED_SESSIONS = ("x11", "wayland")

# Exact token matches only; substrings such as "NotX-Cinnamon" must not match.
_DESKTOP_FAMILIES = (
    ("cinnamon", ("X-Cinnamon", "Cinnamon")),
    ("gnome", ("GNOME", "Unity")),
    ("xfce", ("XFCE",)),
    ("kde", ("KDE", "Plasma")),
)

# Bounds work done on hostile or accidentally huge environment values.
_MAX_ENV_VALUE = 256


def _env_value(env, key):
    """Return a bounded string value, or '' when absent or implausible."""
    value = env.get(key, "")
    if not isinstance(value, str) or len(value) > _MAX_ENV_VALUE:
        return ""
    return value


def _session_type(env):
    value = _env_value(env, "XDG_SESSION_TYPE").strip().lower()
    return value if value in SUPPORTED_SESSIONS else "other-or-unknown"


def _desktop_family(env):
    tokens = [t.strip() for t in _env_value(env, "XDG_CURRENT_DESKTOP").split(":")
              if t.strip()]
    for family, names in _DESKTOP_FAMILIES:
        if any(token in names for token in tokens):
            return family
    return "unknown" if not tokens else "other-or-unknown"


def assess(env, available):
    """Pure evaluation of a session mapping and a tool-availability mapping.

    ``available`` is consulted only for names in ``LAUNCH_TOOLS``. Raw values
    from ``env`` never enter the returned report.
    """
    session = _session_type(env)
    family = _desktop_family(env)
    display_key = ("DISPLAY" if session == "x11" else
                   "WAYLAND_DISPLAY" if session == "wayland" else "")
    has_display = bool(display_key and _env_value(env, display_key).strip())
    tools = {name: bool(available.get(name, False)) for name in LAUNCH_TOOLS}

    blockers = []
    if session == "other-or-unknown":
        blockers.append("unsupported or undeclared session type")
    elif not has_display:
        blockers.append("no graphical display for declared session")
    if not any(tools.values()):
        blockers.append("no resolvable desktop app launch tool")
    else:
        for name, present in tools.items():
            if not present:
                blockers.append(f"launch tool not resolvable: {name}")

    return {
        "schema_version": SCHEMA_VERSION,
        "probe_only": True,
        "app_launch_attempted": False,
        "desktop_acceptance": "NOT_RUN",
        "visual_acceptance": "NOT_RUN",
        "qt_runtime_test": "NOT_RUN",
        "status": "CAPABLE" if not blockers else "BLOCKED",
        "session_type": session,
        "desktop_family": family,
        "graphical_display_present": has_display,
        "runtime_dir_present": bool(_env_value(env, "XDG_RUNTIME_DIR")),
        "launch_tools": tools,
        "blockers": blockers,
    }


def collect(environ=None, which=None):
    """Single-shot host probe. ``which`` only resolves names; nothing runs."""
    env = os.environ if environ is None else environ
    resolver = shutil.which if which is None else which
    available = {name: resolver(name) is not None for name in LAUNCH_TOOLS}
    return assess(env, available)
