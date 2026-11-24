"""Read-only Qt plugin evidence inspector for the Classic Qt prototype.

Reports which Qt image and QPA platform plugin files are observable on disk
and whether a supplied Qt version meets the prototype's Qt 6.4 baseline.
The module never imports Qt, starts a process, changes the environment,
installs packages or writes files. Evidence here is not proof that a
compiled Qt application or a Linux Mint session works.
"""
import argparse
import json
import os
from pathlib import Path


# prototype/classic/CMakeLists.txt: find_package(Qt6 6.4 REQUIRED ...)
MAJOR_QT = 6
MIN_QT = (6, 4)

# The wallpaper and dock artwork are SVG; main.cpp reports a decode failure
# when the Qt SVG image plugin is absent.
REQUIRED_IMAGE_PLUGINS = ("qsvg",)

# QPA plugin required for the declared session type.
SESSION_PLATFORM_PLUGINS = {
    "x11": ("qxcb",),
    "wayland": ("qwayland",),
    "headless": ("qoffscreen", "qminimal"),
}

MAX_NAME_BYTES = 120
MAX_ENTRIES = 512


def normalize_plugin_name(filename):
    """Return a lowercase plugin key from a file name, or None if invalid."""
    if not isinstance(filename, str):
        return None
    name = os.path.basename(filename)
    if not name or len(name) > MAX_NAME_BYTES or not name.isascii():
        return None
    # Gate the raw name before any suffix handling. isprintable() rejects
    # control characters (NUL, tab, newline and 0x1c-0x1f, which Python also
    # treats as whitespace) and isspace() rejects plain whitespace. Without
    # this gate, "qsvg.so\0.evil" was split at ".so" and reported as qsvg.
    if not name.isprintable() or any(char.isspace() for char in name):
        return None
    lowered = name.lower()
    stem = lowered
    for suffix in (".dll", ".dylib", ".so"):
        if lowered.endswith(suffix):
            stem = lowered[:-len(suffix)]
            break
    else:
        # Versioned shared objects such as qsvg.so.6 are legitimate. Accept
        # only an ASCII-digit dotted version after ".so"; any other tail is
        # junk and must never be silently discarded into a plugin key.
        marker = lowered.find(".so.")
        if marker != -1:
            tail = lowered[marker + len(".so."):]
            if tail and all(part.isascii() and part.isdigit()
                            for part in tail.split(".")):
                stem = lowered[:marker]
    if stem.startswith("lib"):
        stem = stem[3:]
    if (len(stem) < 2 or not stem.startswith("q")
            or not stem.isalnum() or any(
                char in stem for char in (" ", "/", "\\", "\0"))):
        return None
    return stem


def parse_version(value):
    """Parse a bounded dotted numeric Qt version, or return None.

    Only ASCII digits are accepted: str.isdigit() also matches Unicode
    numerals that int() may reject (superscript digits raise ValueError) or
    silently coerce (other scripts), escaping this fail-closed contract.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 40:
        return None
    parts = text.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    if not all(part.isascii() and part.isdigit() and len(part) <= 6
               for part in parts):
        return None
    return tuple(int(part) for part in parts)


def version_blocker(version):
    """Return an incompatibility reason, or None when the version is usable."""
    if version is None:
        return "Qt version unavailable or unparseable"
    rendered = ".".join(str(part) for part in version)
    if version[0] != MAJOR_QT:
        return f"incompatible Qt major version {version[0]}; need {MAJOR_QT}"
    minimum = ".".join(str(part) for part in MIN_QT)
    if version < MIN_QT:
        return f"Qt {rendered} below required {minimum}"
    return None


def _plugin_keys(values):
    """Deduplicate and bound an iterable of observed plugin names."""
    result = set()
    for value in values or ():
        if len(result) >= MAX_ENTRIES:
            break
        key = normalize_plugin_name(value)
        if key is not None:
            result.add(key)
    return tuple(sorted(result))


def assess(image_plugins, platform_plugins, qt_version=None, session="unknown",
           required_image=REQUIRED_IMAGE_PLUGINS):
    """Pure, deterministic evaluation of observed plugin evidence."""
    images = _plugin_keys(image_plugins)
    platforms = _plugin_keys(platform_plugins)
    version = qt_version if isinstance(qt_version, tuple) else parse_version(qt_version)
    blockers = []

    incompatible = version_blocker(version)
    if incompatible is not None:
        blockers.append(incompatible)

    missing_image = tuple(
        name for name in required_image if name not in images)
    if missing_image:
        blockers.append("missing Qt image plugin(s): " + ", ".join(missing_image))

    expected = SESSION_PLATFORM_PLUGINS.get(session)
    missing_platform = ()
    if expected is None:
        blockers.append("unknown session type; cannot identify required QPA plugin")
    elif not any(name in platforms for name in expected):
        # Entries are alternatives: qoffscreen OR qminimal satisfies headless.
        missing_platform = expected
        blockers.append(
            "missing Qt platform plugin(s): " + ", ".join(missing_platform))

    return {
        "schema_version": 1,
        "probe_only": True,
        "mint_guest_acceptance": "NOT_RUN",
        "runtime_functional_test": "NOT_RUN",
        "visual_acceptance": "NOT_RUN",
        "status": "BLOCKED" if blockers else "OK",
        "qt_version": ".".join(str(part) for part in version) if version else None,
        "qt_version_compatible": incompatible is None,
        "minimum_qt": ".".join(str(part) for part in MIN_QT),
        "session": session if expected is not None else "other-or-unknown",
        "expected_platform_plugins": list(expected or ()),
        "image_plugins": list(images),
        "platform_plugins": list(platforms),
        "missing_image_plugins": list(missing_image),
        "missing_platform_plugins": list(missing_platform),
        "svg_plugin_present": "qsvg" in images,
        "platform_plugin_present": bool(expected) and not missing_platform,
        "blockers": blockers,
    }


def collect(plugins_root, session="unknown", qt_version=None):
    """One-shot read-only scan of a Qt plugins directory.

    Only the immediate imageformats/ and platforms/ children are read.
    Symlinks and nested directories are skipped; scanning stops at
    MAX_ENTRIES per category. The version must be supplied by the caller so
    this function never executes Qt or pkg-config.
    """
    root = Path(plugins_root)
    observed = {}
    for category in ("imageformats", "platforms"):
        keys = []
        try:
            with os.scandir(root / category) as entries:
                for entry in entries:
                    if len(keys) >= MAX_ENTRIES:
                        break
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    key = normalize_plugin_name(entry.name)
                    if key is not None:
                        keys.append(key)
        except (OSError, ValueError):
            keys = []
        observed[category] = keys
    return assess(observed["imageformats"], observed["platforms"],
                  qt_version, session)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugins-root",
                        help="Qt plugins directory to inspect read-only")
    parser.add_argument("--session", default="unknown",
                        help="session type: x11, wayland or headless")
    parser.add_argument("--qt-version",
                        help="Qt version reported by pkg-config or qmake")
    parser.add_argument("--json", action="store_true", help="print JSON evidence")
    args = parser.parse_args(argv)

    if args.plugins_root:
        report = collect(args.plugins_root, args.session, args.qt_version)
    else:
        report = assess((), (), args.qt_version, args.session)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"QT_PLUGIN_DISCOVERY_{report['status']}: "
              f"Qt={report['qt_version'] or 'unknown'} "
              f"svg={report['svg_plugin_present']} "
              f"platform={report['platform_plugin_present']}")
        for blocker in report["blockers"]:
            print(f"BLOCKED: {blocker}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
