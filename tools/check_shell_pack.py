#!/usr/bin/env python3
"""Offline safety/shape checker for the proposed Canopy Shell Pack v1 contract.

This checker never installs, imports, evaluates, or executes pack code.
A VALID manifest does NOT imply that a pack is trusted or safe to run.
"""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys


MANIFEST_VERSION = 1
HOST_API_MAJOR = 1
MAX_MANIFEST_BYTES = 16_384
MAX_QML_ENTRYPOINT_BYTES = 1_048_576
REQUIRED_FIELDS = frozenset({
    "manifest_version", "id", "name", "description", "shell_api",
    "kind", "ui_engine", "entrypoint", "capabilities", "switch_strategy",
    "permissions",
})
CAPABILITIES = frozenset({
    "app-launcher", "dock", "top-bar", "taskbar", "workspace-list",
    "window-list", "system-status", "settings-panel",
})
PACK_ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*){2,}", re.ASCII)
NAME_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
ENTRY_COMPONENT = re.compile(r"[A-Za-z][A-Za-z0-9_-]*", re.ASCII)
ENTRY_FILE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\.qml", re.ASCII)


class PackValidationError(ValueError):
    """Untrusted pack descriptor is invalid or unsupported."""


def require_real_path_components(path, message):
    """Raise PackValidationError if any component of *path* is a symlink.

    A leaf-only ``is_symlink()`` check is defeated by an aliased parent: the
    whole catalog then resolves outside the declared tree while the caller
    still records the declared path. Walk every component from the anchor
    with ``lstat`` (never ``resolve``), so relative inputs and ordinary
    multi-component Windows temp paths behave exactly as before.
    """
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise PackValidationError(message) from exc
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise PackValidationError(message)
    if os.pardir in Path(raw).parts:
        # abspath collapses '..' lexically, which could conceal an alias.
        raise PackValidationError(message)
    try:
        parts = Path(os.path.abspath(raw)).parts
    except (OSError, ValueError) as exc:
        raise PackValidationError(message) from exc
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except OSError as exc:
            raise PackValidationError(message) from exc
        if stat.S_ISLNK(mode):
            raise PackValidationError(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise PackValidationError(f"invalid JSON constant: {value}")


def _nonempty_string(value, name, maximum):
    if (not isinstance(value, str) or not value or len(value) > maximum
            or value != value.strip() or NAME_CONTROL.search(value)):
        raise PackValidationError(f"{name} must be a clean string, max {maximum} characters")


def _validate_entrypoint(pack_root, entrypoint):
    # Keep all v1 QML entrypoints in a fixed, local UI subtree.
    if not isinstance(entrypoint, str):
        raise PackValidationError("entrypoint must be a local relative QML path")
    parts = entrypoint.split("/")
    if (len(parts) < 2 or parts[0] != "ui"
            or any(part in ("", ".", "..") for part in parts)
            or any(not ENTRY_COMPONENT.fullmatch(p) for p in parts[1:-1])
            or not ENTRY_FILE.fullmatch(parts[-1])):
        raise PackValidationError("entrypoint must be a safe relative ui/*.qml path")
    target = pack_root
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise PackValidationError("entrypoint cannot traverse symlinks")
    if not target.is_file():
        raise PackValidationError("entrypoint QML file is missing")
    if target.stat().st_size > MAX_QML_ENTRYPOINT_BYTES:
        raise PackValidationError("entrypoint QML file exceeds 1 MiB")
    return target


def validate_pack(pack_root: Path) -> dict:
    """Validate an untrusted local pack without running its UI code."""
    pack_root = Path(pack_root)
    if pack_root.is_symlink() or not pack_root.is_dir():
        raise PackValidationError("pack must be a real local directory")
    # The leaf check above is defeated by an aliased ancestor; fail closed on
    # every component so the descriptor cannot escape the declared pack path.
    require_real_path_components(pack_root, "pack must be a real local directory")
    manifest_path = pack_root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PackValidationError("manifest.json must be a regular local file")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise PackValidationError("manifest exceeds 16 KiB")
    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackValidationError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PackValidationError("manifest must be one JSON object")
    if manifest.keys() != REQUIRED_FIELDS:
        missing = sorted(REQUIRED_FIELDS - manifest.keys())
        extra = sorted(manifest.keys() - REQUIRED_FIELDS)
        raise PackValidationError(f"unexpected manifest fields; missing={missing}, extra={extra}")

    # Avoid Python's bool-is-an-int pitfall for version fields.
    for key, expected in (("manifest_version", MANIFEST_VERSION),
                          ("shell_api", HOST_API_MAJOR)):
        if type(manifest[key]) is not int or manifest[key] != expected:
            raise PackValidationError(f"unsupported {key}: expected {expected}")

    pack_id = manifest["id"]
    if (not isinstance(pack_id, str) or len(pack_id) > 128
            or not PACK_ID.fullmatch(pack_id)
            or pack_id.startswith("org.canopy.")):
        raise PackValidationError("id must be a nonreserved reverse-DNS lowercase name")
    _nonempty_string(manifest["name"], "name", 80)
    _nonempty_string(manifest["description"], "description", 240)

    if manifest["kind"] != "presentation":
        raise PackValidationError("v1 only supports presentation shell packs")
    if manifest["ui_engine"] != "qt-qml":
        raise PackValidationError("v1 only supports Qt/QML shell packs")
    if manifest["switch_strategy"] != "same-session":
        raise PackValidationError("v1 packs declare a same-session switching goal")
    if (not isinstance(manifest["permissions"], list)
            or manifest["permissions"]):
        raise PackValidationError("v1 packs cannot declare permissions")

    caps = manifest["capabilities"]
    if (not isinstance(caps, list) or not caps
            or any(not isinstance(cap, str) or cap not in CAPABILITIES
                   for cap in caps)
            or len(set(caps)) != len(caps)):
        raise PackValidationError("capabilities must be unique known host affordances")
    _validate_entrypoint(pack_root, manifest["entrypoint"])
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path, help="local Shell Pack directory")
    args = parser.parse_args(argv)
    try:
        descriptor = validate_pack(args.pack)
    except (PackValidationError, OSError) as exc:
        print(f"SHELL_PACK_FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"SHELL_PACK_MANIFEST_PASS: {descriptor['id']} "
          "(metadata only; no runtime loading or trust verification)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
