#!/usr/bin/env python3
"""Build a strictly user-level, reversible Canopy Classic preview package.

This QA helper assembles an EXPERIMENTAL APPLICATION PREVIEW. It is never a
complete session, compositor, display manager or login-manager replacement,
and it never changes the user's desktop or the approved dock geometry.

It builds on existing project mechanisms and changes none of them:

  * CMake target ``canopy-classic-spike`` in prototype/classic/CMakeLists.txt
    owns compilation and any RUNTIME DESTINATION install. This helper never
    builds, downloads or installs system-wide; it requires an already-compiled
    binary supplied explicitly with --binary.

  * tools/prepare_approved_art.py owns the exact-art manifest and the nine
    SHA-locked source PNGs. No substitute or generated art is ever accepted.

  * tools/register_classic_preview.py owns the single reversible, unprivileged
    desktop menu entry. Registration and unregistration are delegated to it.

All writes stay under XDG_DATA_HOME (the ordinary desktop user). No sudo, no
background services, no network, no session or display-manager changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

if __package__:
    from tools import prepare_approved_art as art
    from tools import register_classic_preview as reg
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools import prepare_approved_art as art
    from tools import register_classic_preview as reg

PACKAGE_DIRNAME = "classic-preview-package"
BINARY_NAME = "canopy-classic-spike"
MANIFEST_NAME = "package.json"
SCHEMA = 1
MAX_BINARY_BYTES = 250_000_000
MAX_MANIFEST_BYTES = 16_384
HASH64 = re.compile(r"[0-9a-f]{64}\Z")
BANNED_EXEC = ('"', "\\", "$", chr(96), "%", "\n", "\r", "\x00")
SCOPE = ("experimental application preview; not a session, compositor, "
         "desktop or login-manager replacement")
PACKAGE_KIND = "canopy-classic-preview-package"


class PackageError(ValueError):
    pass


def _euid():
    getter = getattr(os, "geteuid", None)
    return getter() if getter is not None else 1000


def _is_executable(path):
    if os.name == "nt":
        return True
    return os.access(path, os.X_OK)


def data_home():
    chosen = os.environ.get("XDG_DATA_HOME")
    if chosen:
        path = Path(chosen)
        if not path.is_absolute():
            raise PackageError("XDG_DATA_HOME must be absolute")
        return path
    return Path.home() / ".local" / "share"


def package_paths(home):
    home = Path(home)
    root = home / "canopy" / PACKAGE_DIRNAME
    return {
        "data": home,
        "canopy": home / "canopy",
        "root": root,
        "bin": root / "bin" / BINARY_NAME,
        "art": root / "art",
        "manifest": root / MANIFEST_NAME,
        "apps": home / "applications",
        "desktop": home / "applications" / reg.DESKTOP,
    }


def _require_unprivileged():
    if _euid() == 0:
        raise PackageError("root/system-wide packaging refused")


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained(root, child):
    root_r = Path(root).resolve()
    child_r = Path(child).resolve()
    return child_r == root_r or root_r in child_r.parents


def _safe_binary(binary):
    path = Path(binary)
    if not path.is_absolute():
        raise PackageError("compiled binary path must be absolute")
    if path.is_symlink():
        raise PackageError("compiled binary must be a regular file, not a symlink")
    if not path.is_file():
        raise PackageError("compiled binary is missing")
    size = path.stat().st_size
    if size <= 0 or size > MAX_BINARY_BYTES:
        raise PackageError("compiled binary size is outside the safe range")
    if not _is_executable(path):
        raise PackageError("compiled binary is not executable")
    return path


def _approved_entries(manifest_path):
    try:
        manifest = art.read_manifest(Path(manifest_path))
    except art.ArtworkError as exc:
        raise PackageError("invalid approved-art manifest: " + str(exc)) from exc
    try:
        entries = [*manifest["icons"], manifest["wallpaper"]]
    except (KeyError, TypeError) as exc:
        raise PackageError("approved-art manifest is incomplete") from exc
    if len(entries) != 9 or len({item["path"] for item in entries}) != 9:
        raise PackageError("approved-art manifest must describe nine unique assets")
    for item in entries:
        rel = Path(item["path"])
        if (rel.is_absolute() or ".." in rel.parts or "\\" in item["path"]
                or not HASH64.fullmatch(item["sha256"])):
            raise PackageError("unsafe approved-art manifest entry")
    return manifest, entries


def _safe_art_dir(art_dir, entries):
    directory = Path(art_dir)
    if not directory.is_absolute():
        raise PackageError("approved-art directory must be absolute")
    if directory.is_symlink() or not directory.is_dir():
        raise PackageError("approved-art directory must be a real directory")
    for item in entries:
        source = directory / item["path"]
        if not _contained(directory, source):
            raise PackageError("approved-art path escapes its directory")
        try:
            art.check_exact(source, item["sha256"])
        except art.ArtworkError as exc:
            raise PackageError("approved art rejected: " + str(exc)) from exc
    return directory


def _banned_exec():
    # The native path separator is safe in an Exec path; every other shell or
    # field-code metacharacter stays banned. On Linux this still rejects "\\".
    return tuple(ch for ch in BANNED_EXEC if ch != os.sep)


def _quote(value):
    text = str(value)
    if any(ch in text for ch in _banned_exec()):
        raise PackageError("unsupported character in desktop Exec path")
    return '"' + text + '"'


def _command(binary, art_dir, wallpaper=None):
    args = [str(binary), "--approved-art-dir", str(art_dir)]
    if wallpaper is not None:
        args += ["--landscape-wallpaper", str(wallpaper)]
    return " ".join(_quote(item) for item in args)


def _target(home, binary, art_dir, *, manifest_path=art.MANIFEST):
    p = package_paths(home)
    source_binary = _safe_binary(binary)
    manifest, entries = _approved_entries(manifest_path)
    source_art = _safe_art_dir(art_dir, entries)
    wallpaper_rel = manifest["wallpaper"]["path"]
    staged_binary = p["bin"]
    staged_art = p["art"]
    command = _command(staged_binary, staged_art, staged_art / wallpaper_rel)
    return {
        "binary": source_binary,
        "binary_sha256": _sha256_file(source_binary),
        "art": source_art,
        "entries": entries,
        "wallpaper_rel": wallpaper_rel,
        "command": command,
    }


def make_plan(home, binary, art_dir, *, manifest_path=art.MANIFEST):
    """Validate inputs and describe the package without writing anything."""
    _require_unprivileged()
    p = package_paths(home)
    info = _target(home, binary, art_dir, manifest_path=manifest_path)
    return {
        "schema": SCHEMA,
        "kind": "dry-run",
        "home": str(home),
        "package_root": str(p["root"]),
        "staged_binary": str(p["bin"]),
        "staged_art": str(p["art"]),
        "staged_wallpaper": str(p["art"] / info["wallpaper_rel"]),
        "source_binary": str(info["binary"]),
        "source_binary_sha256": info["binary_sha256"],
        "source_art_dir": str(info["art"]),
        "assets": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in info["entries"]
        ],
        "desktop_exec": info["command"],
        "desktop_entry": str(p["desktop"]),
        "registration": "tools/register_classic_preview.py install",
        "writes_files": False,
        "scope": SCOPE,
        "not_a": ["session", "compositor", "display manager", "login manager"],
        "requires_sudo": False,
    }


def _safe_roots(p):
    for key in ("data", "canopy", "root", "apps"):
        path = p[key]
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise PackageError("unsafe packaging directory: " + key)
    if p["desktop"].is_symlink():
        raise PackageError("unsafe desktop entry symlink")


def _stage_package(p, info):
    p["root"].parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".canopy-package-",
                                     dir=str(p["root"].parent)) as temp:
        stage = Path(temp)
        binary_stage = stage / "bin" / BINARY_NAME
        binary_stage.parent.mkdir(parents=True)
        shutil.copyfile(info["binary"], binary_stage)
        binary_stage.chmod(0o755)
        if _sha256_file(binary_stage) != info["binary_sha256"]:
            raise PackageError("binary changed while staging")
        art_stage = stage / "art"
        art_stage.mkdir()
        for item in info["entries"]:
            target = art_stage / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(info["art"] / item["path"], target)
            art.check_exact(target, item["sha256"])
        stage.rename(p["root"])


def _write_manifest(p, info):
    record = {
        "schema": SCHEMA,
        "kind": PACKAGE_KIND,
        "binary": {"path": "bin/" + BINARY_NAME,
                   "sha256": info["binary_sha256"]},
        "art": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in info["entries"]
        ],
        "wallpaper": info["wallpaper_rel"],
        "desktop_exec": info["command"],
        "registration": reg.DESKTOP,
        "scope": SCOPE,
    }
    data = json.dumps(record, sort_keys=True, indent=2).encode("utf-8")
    with p["manifest"].open("xb") as handle:
        handle.write(data)
    p["manifest"].chmod(0o600)


def _read_manifest(p):
    path = p["manifest"]
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if (not isinstance(record, dict) or record.get("schema") != SCHEMA
            or record.get("kind") != PACKAGE_KIND):
        return None
    return record


def _verify_package(p, record):
    if (not isinstance(record, dict) or p["bin"].is_symlink()
            or not p["bin"].is_file()):
        return False
    try:
        if _sha256_file(p["bin"]) != record["binary"]["sha256"]:
            return False
    except (KeyError, TypeError, OSError, ValueError):
        return False
    art_root = p["art"]
    if art_root.is_symlink() or not art_root.is_dir():
        return False
    try:
        owned = [art_root / item["path"] for item in record["art"]]
    except (KeyError, TypeError):
        return False
    if len(owned) != 9:
        return False
    for target in owned:
        if (not _contained(art_root, target) or target.is_symlink()
                or not target.is_file()):
            return False
    expected = {p["bin"], p["manifest"], *owned}
    try:
        expected_r = {item.resolve() for item in expected}
    except OSError:
        return False
    for path in p["root"].rglob("*"):
        if path.is_symlink():
            return False
        if not path.is_dir() and path.resolve() not in expected_r:
            return False
    for target, item in zip(owned, record["art"]):
        if _sha256_file(target) != item["sha256"]:
            return False
    return True


def status(home):
    p = package_paths(home)
    try:
        _safe_roots(p)
    except PackageError:
        return "UNSAFE"
    record = _read_manifest(p)
    registration = reg.status(home)
    if record is None and registration == "NOT_INSTALLED":
        return "NOT_INSTALLED"
    if record is None or registration != "INSTALLED":
        return "MODIFIED_OR_UNMANAGED"
    return "INSTALLED" if _verify_package(p, record) else "MODIFIED_OR_UNMANAGED"


def _register(home, info):
    """Install the same menu entry/marker as register_classic_preview.py.

    The payload and SHA-256 ownership marker are byte-compatible with that
    tool so reg.status()/reg.uninstall() keep working. Only the Exec quoting is
    implemented here because it must tolerate the native path separator.
    """
    rp = reg.paths(home)
    payload = (
        "[Desktop Entry]\nType=Application\nVersion=1.0\n"
        "Name=Canopy Classic Preview\n"
        "Comment=Experimental application, not a replacement Cinnamon session\n"
        "Exec=" + info["command"] + "\n"
        "Terminal=false\nIcon=computer\nCategories=Utility;\n"
        "StartupNotify=false\nX-Canopy-Preview=true\n"
    ).encode("utf-8")
    marker = json.dumps({"schema": 1, "sha256": reg._sha(payload)},
                        sort_keys=True).encode("utf-8")
    for key in ("data", "parent", "folder", "apps"):
        path = rp[key]
        if path.is_symlink():
            raise PackageError("unsafe registration directory")
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if any(rp["folder"].iterdir()):
        raise PackageError("unmanaged preview folder is not empty")
    created = []
    try:
        for target, data, perms in (
                (rp["desktop"], payload, 0o644),
                (rp["manifest"], marker, 0o600)):
            with target.open("xb") as handle:
                created.append(target)
                handle.write(data)
            target.chmod(perms)
    except (OSError, ValueError):
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise


def install(home, binary, art_dir, *, manifest_path=art.MANIFEST):
    _require_unprivileged()
    home = Path(home)
    p = package_paths(home)
    info = _target(home, binary, art_dir, manifest_path=manifest_path)
    _safe_roots(p)
    if status(home) != "NOT_INSTALLED":
        raise PackageError("existing package or registration: refusing overwrite")
    if reg.status(home) != "NOT_INSTALLED":
        raise PackageError("existing preview registration: refusing overwrite")
    staged = False
    registered = False
    try:
        _stage_package(p, info)
        staged = True
        _register(home, info)
        registered = True
        _write_manifest(p, info)
    except Exception:
        if registered:
            try:
                reg.uninstall(home)
            except Exception:
                pass
        if staged:
            shutil.rmtree(p["root"], ignore_errors=True)
        raise
    return p["manifest"]


def uninstall(home):
    _require_unprivileged()
    home = Path(home)
    p = package_paths(home)
    if status(home) != "INSTALLED":
        raise PackageError("not exact-byte owned; removed nothing")
    record = _read_manifest(p)
    if not _verify_package(p, record):
        raise PackageError("package changed during uninstall")
    if reg.status(home) != "INSTALLED":
        raise PackageError("registration changed during uninstall")
    reg.uninstall(home)
    shutil.rmtree(p["root"])
    return "UNINSTALLED"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "install"):
        node = sub.add_parser(name)
        node.add_argument("--binary", type=Path, required=True)
        node.add_argument("--approved-art-dir", type=Path, required=True)
        node.add_argument("--manifest", type=Path, default=art.MANIFEST)
    sub.add_parser("status")
    sub.add_parser("uninstall")
    args = parser.parse_args(argv)
    try:
        home = data_home()
        if args.command == "plan":
            result = make_plan(home, args.binary, args.approved_art_dir,
                               manifest_path=args.manifest)
            print(json.dumps(result, sort_keys=True, indent=2))
        elif args.command == "install":
            result = install(home, args.binary, args.approved_art_dir,
                             manifest_path=args.manifest)
            print("CANOPY_PACKAGE_INSTALLED:", result)
        elif args.command == "status":
            print("CANOPY_PACKAGE_" + status(home))
        else:
            print("CANOPY_PACKAGE_" + uninstall(home))
    except (PackageError, art.ArtworkError, reg.RegistrationError,
            OSError, ValueError, KeyError) as exc:
        print("CANOPY_PACKAGE_FAIL:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
