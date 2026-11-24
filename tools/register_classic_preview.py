#!/usr/bin/env python3
"""Install a reversible, per-user Canopy Classic application MENU entry.

No root, session changes, display manager changes, daemon or app launch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

DESKTOP = "org.canopy.ClassicPreview.desktop"
HASH = re.compile(r"[0-9a-f]{64}\Z")


class RegistrationError(ValueError):
    pass


def _home_path(home):
    """Normalize a caller-supplied home, failing closed with a domain error."""
    if isinstance(home, bool) or not isinstance(home, (str, os.PathLike)):
        raise RegistrationError("home must be a string or path-like value")
    try:
        return Path(home)
    except (TypeError, ValueError, OSError) as exc:
        raise RegistrationError("home must be a string or path-like value") from exc


def paths(home):
    home = _home_path(home)
    folder = home / "canopy" / "classic-preview"
    return {
        "data": home,
        "parent": folder.parent,
        "folder": folder,
        "apps": home / "applications",
        "desktop": home / "applications" / DESKTOP,
        "manifest": folder / "ownership.json",
    }


def data_home():
    chosen = os.environ.get("XDG_DATA_HOME")
    if chosen:
        if not Path(chosen).is_absolute():
            raise RegistrationError("XDG_DATA_HOME must be absolute")
        return Path(chosen)
    return Path.home() / ".local" / "share"


def _require_real_path_components(path, message):
    """Raise RegistrationError if any existing component of *path* is a link.

    A leaf-only ``is_symlink()`` check is defeated by an aliased parent: the
    resource or registration directory resolves outside the declared tree
    while the caller still records the declared path. Walk every component
    with ``lstat`` (never ``resolve``) so ordinary multi-component Windows
    temp paths behave as before. ``..`` is refused rather than collapsed
    lexically, which could conceal the alias. Installation creates missing
    directories, so the walk stops at the first component that does not exist
    yet; no link can exist beneath a missing component.
    """
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise RegistrationError(message) from exc
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise RegistrationError(message)
    if os.pardir in Path(raw).parts:
        raise RegistrationError(message)
    try:
        parts = Path(os.path.abspath(raw)).parts
    except (OSError, ValueError) as exc:
        raise RegistrationError(message) from exc
    if not parts:
        raise RegistrationError(message)
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise RegistrationError(message) from exc
        if stat.S_ISLNK(mode):
            raise RegistrationError(message)


def _safe_folders(p):
    for key in ("data", "parent", "folder", "apps"):
        path = p[key]
        if path.exists() and not path.is_dir():
            raise RegistrationError("unsafe registration directory")
        _require_real_path_components(path, "unsafe registration directory")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _marker(p):
    f = p["manifest"]
    if f.is_symlink() or not f.is_file() or f.stat().st_size > 4096:
        return None
    try:
        entry = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if (not isinstance(entry, dict)
            or set(entry) != {"schema", "sha256"}
            or type(entry["schema"]) is not int or entry["schema"] != 1
            or not isinstance(entry["sha256"], str)
            or not HASH.fullmatch(entry["sha256"])):
        return None
    return entry


def status(home):
    try:
        p = paths(home)
        _safe_folders(p)
    except RegistrationError:
        return "UNSAFE"
    f, m = p["desktop"], p["manifest"]
    if f.is_symlink() or m.is_symlink():
        return "UNSAFE"
    if not f.exists() and not m.exists():
        return "NOT_INSTALLED"
    record = _marker(p)
    if record is None or not f.is_file() or f.stat().st_size > 8192:
        return "MODIFIED_OR_UNMANAGED"
    return "INSTALLED" if _sha(f.read_bytes()) == record["sha256"] else "MODIFIED_OR_UNMANAGED"


def _resource(obj, name, directory=False):
    if obj is None:
        return None
    message = name + " must be an existing absolute non-symlink path"
    if isinstance(obj, bool) or not isinstance(obj, (str, os.PathLike)):
        raise RegistrationError(message)
    try:
        p = Path(obj)
    except (TypeError, ValueError, OSError) as exc:
        raise RegistrationError(message) from exc
    if (not p.is_absolute() or p.is_symlink()
            or (not p.is_dir() if directory else not p.is_file())):
        raise RegistrationError(message)
    _require_real_path_components(p, message)
    return str(p)


def _quote(value):
    # Desktop Entry Exec field codes are not shell quoting.
    # Permit spaces, but reject tricky chars rather than use a shell.
    banned = ('"', "$", chr(96), "%", chr(10), chr(13), chr(0))
    sep = chr(92)
    if sep in value:
        if os.name != "nt":
            raise RegistrationError("unsupported character in desktop Exec path")
        # Native absolute paths use backslash separators. Accept only a
        # drive-qualified prefix; UNC, doubled and trailing separators stay refused.
        if (len(value) < 3 or not value[0].isalpha() or value[1:3] != ":" + sep
                or sep + sep in value or value.endswith(sep)):
            raise RegistrationError("unsupported character in desktop Exec path")
    if any(ch in value for ch in banned):
        raise RegistrationError("unsupported character in desktop Exec path")
    return '"' + value + '"' 


def _effective_uid():
    """Return the POSIX effective UID, or None when the probe is unavailable."""
    getter = getattr(os, "geteuid", None)
    return None if getter is None else getter()


def _unprivileged():
    # Shared by pure validators: without a POSIX probe there is no root to
    # refuse, so path validation may continue; writes use the stricter guard.
    if _effective_uid() == 0:
        raise RegistrationError("root/system-wide operation refused")


def _require_unprivileged():
    if _effective_uid() is None:
        # Fail closed: an operation that writes cannot prove it is unprivileged.
        raise RegistrationError("privilege check unavailable: operation refused")
    _unprivileged()


def install(home, binary, *, art=None, wallpaper=None, terminal=None, native_apps=False):
    _require_unprivileged()
    p = paths(home)
    _safe_folders(p)
    if status(home) != "NOT_INSTALLED":
        raise RegistrationError("existing registration: refusing overwrite")
    exe = _resource(binary, "Canopy binary")
    if exe is None:
        raise RegistrationError(
            "Canopy binary must be an existing absolute non-symlink path")
    if not os.access(exe, os.X_OK):
        raise RegistrationError("Canopy binary is not executable")
    art = _resource(art, "approved artwork", directory=True)
    wallpaper = _resource(wallpaper, "wallpaper")
    terminal = _resource(terminal, "Terminal candidate")
    if terminal and not art:
        raise RegistrationError("Terminal candidate requires approved art")
    args = [exe]
    for flag, value in (
        ("--approved-art-dir", art),
        ("--landscape-wallpaper", wallpaper),
        ("--terminal-refinement", terminal),
    ):
        if value:
            args.extend((flag, value))
    if native_apps:
        args.append("--enable-system-apps")
    command = " ".join(_quote(x) for x in args)
    payload = (
        "[Desktop Entry]\nType=Application\nVersion=1.0\n"
        "Name=Canopy Classic Preview\n"
        "Comment=Experimental application, not a replacement Cinnamon session\n"
        "Exec=" + command + "\n"
        "Terminal=false\nIcon=computer\nCategories=Utility;\n"
        "StartupNotify=false\nX-Canopy-Preview=true\n"
    ).encode("utf-8")
    marker = json.dumps({"schema": 1, "sha256": _sha(payload)},
                        sort_keys=True).encode("utf-8")
    for key in ("data", "parent", "folder", "apps"):
        path = p[key]
        _require_real_path_components(path, "unsafe linked directory")
        if path.is_symlink():
            raise RegistrationError("unsafe linked directory")
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if any(p["folder"].iterdir()):
        raise RegistrationError("unmanaged preview folder is not empty")
    created = []
    try:
        for f, data, perms in (
            (p["desktop"], payload, 0o644),
            (p["manifest"], marker, 0o600),
        ):
            with f.open("xb") as handle:
                created.append(f)
                handle.write(data)
            f.chmod(perms)
    except (OSError, ValueError):
        for f in reversed(created):
            f.unlink(missing_ok=True)
        raise
    return p["desktop"]


def uninstall(home):
    _require_unprivileged()
    p = paths(home)
    if status(home) != "INSTALLED":
        raise RegistrationError("not exact-byte owned; removed nothing")
    marker = _marker(p)
    if (marker is None or p["desktop"].is_symlink()
            or _sha(p["desktop"].read_bytes()) != marker["sha256"]):
        raise RegistrationError("registration changed during uninstall")
    p["desktop"].unlink()
    p["manifest"].unlink()
    # Retain directories, which may contain unrelated files.
    return "UNINSTALLED"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("install")
    add.add_argument("--binary", required=True, type=Path)
    add.add_argument("--approved-art-dir", type=Path)
    add.add_argument("--landscape-wallpaper", type=Path)
    add.add_argument("--terminal-refinement", type=Path)
    add.add_argument("--enable-system-apps", action="store_true")
    sub.add_parser("status")
    sub.add_parser("uninstall")
    a = parser.parse_args(argv)
    try:
        home = data_home()
        if a.command == "install":
            result = install(home, a.binary, art=a.approved_art_dir,
                             wallpaper=a.landscape_wallpaper,
                             terminal=a.terminal_refinement,
                             native_apps=a.enable_system_apps)
            print("CANOPY_PREVIEW_REGISTERED:", result)
        elif a.command == "uninstall":
            print("CANOPY_PREVIEW_" + uninstall(home))
        else:
            print("CANOPY_PREVIEW_" + status(home))
    except (RegistrationError, ValueError, OSError) as exc:
        print("CANOPY_PREVIEW_FAIL:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
