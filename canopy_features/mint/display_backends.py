"""Read-only display-backend probe for safe Mint Qt testing.

Chooses a Qt platform plugin from session/display facts only, and falls back
to the software-rendered ``offscreen`` plugin when no usable display exists.
This is a probe: it never launches Qt, alters a session, or claims Mint, Qt or
visual acceptance. ``plan`` is pure; ``collect`` reads only ``os.environ``.
"""
import argparse
import json
import os

from tools.mint_guest_preflight import assess as _preflight_assess

SCHEMA_VERSION = 1
SOFTWARE_BACKEND = "offscreen"
SESSION_BACKENDS = {"x11": "xcb", "wayland": "wayland"}


def _display_facts(env):
    """Reuse the Mint preflight session/display consistency rule only.

    ``assess`` also reports release, tool and Qt readiness that needs facts
    this probe intentionally does not collect; those fields are ignored.
    """
    report = _preflight_assess({}, env, {}, None)
    session = report["session_type"]
    if session not in SESSION_BACKENDS:
        session = "unknown"
    return session, bool(report["graphical_display_present"])


def plan(env):
    """Return a bounded, privacy-minimized backend decision for ``env``."""
    session, display_present = _display_facts(env)
    if session in SESSION_BACKENDS and display_present:
        backend = SESSION_BACKENDS[session]
        reasons = []
    else:
        backend = SOFTWARE_BACKEND
        detail = ("session type missing or unsupported" if session == "unknown"
                  else "session declares " + session + " but no display is present")
        reasons = [detail + "; using software-render fallback (offscreen)"]
    return {
        "schema_version": SCHEMA_VERSION,
        "probe_only": True,
        "backend": backend,
        "software_render": backend == SOFTWARE_BACKEND,
        "session_type": session,
        "display_present": display_present,
        "qt_qpa_platform": backend,
        "env_overlay": {"QT_QPA_PLATFORM": backend},
        "reasons": reasons,
        "runtime_functional_test": "NOT_RUN",
        "mint_guest_acceptance": "NOT_RUN",
        "visual_acceptance": "NOT_RUN",
    }


def collect():
    """Probe the current process environment; no files, processes or network."""
    return plan(dict(os.environ))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON decision")
    args = parser.parse_args(argv)
    result = collect()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("DISPLAY_BACKEND_" + result["backend"].upper())
        for reason in result["reasons"]:
            print("SOFTWARE_FALLBACK: " + reason)
    # A software fallback is a safe, successful outcome, not a failed probe.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
