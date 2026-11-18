#!/usr/bin/env python3
"""Canopy Classic: reversible Cinnamon layout experiment (dry-run default)."""
import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

SCHEMA = "org.cinnamon"
KEYS = ("panels-enabled", "enabled-applets")
FORMAT = 1


class LayoutError(Exception):
    pass


def decode_strv(raw):
    try:
        items = ast.literal_eval(raw)
    except (SyntaxError, ValueError) as exc:
        raise LayoutError("Unexpected gsettings array") from exc
    if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
        raise LayoutError("Expected array of strings")
    return items


def encode_strv(items):
    return "[" + ", ".join(repr(x) for x in items) + "]"


def build_layout(panels, applets):
    """Change only a single-monitor default Cinnamon panel layout."""
    if panels != ["1:0:bottom"]:
        raise LayoutError("Requires one bottom panel on the primary display; custom layouts are not touched")
    top, bottom = [], []
    menus = windows = 0
    for entry in applets:
        fields = entry.split(":", 4)
        if len(fields) not in (4, 5) or fields[0] != "panel1" or fields[1] not in ("left", "center", "right") or not fields[2].isdigit() or not fields[3]:
            raise LayoutError("Unsupported applet entry: " + entry)
        name = fields[3]
        if name == "grouped-window-list@cinnamon.org":
            windows += 1
            bottom.append(":".join(["panel2", "center", "0"] + fields[3:]))
        elif name == "menu@cinnamon.org":
            menus += 1
            top.append(":".join(["panel1", "left", "0"] + fields[3:]))
        else:
            top.append(":".join(["panel1", "right", str(len(top) + 1)] + fields[3:]))
    if menus != 1 or windows != 1:
        raise LayoutError("One native menu and grouped-window-list are required")
    return ["1:0:top", "2:0:bottom"], top + bottom


def get_setting(key):
    return subprocess.run(["gsettings", "get", SCHEMA, key], check=True, text=True, capture_output=True).stdout.strip()


def set_setting(key, raw):
    subprocess.run(["gsettings", "set", SCHEMA, key, raw], check=True, text=True, capture_output=True)


def safe_save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        raise LayoutError("Backup already exists: " + str(path))
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Save settings backup, then apply layout")
    mode.add_argument("--restore", action="store_true", help="Restore saved panel settings")
    p.add_argument("--backup", type=Path, default=Path.home() / ".local/state/canopy/cinnamon-layout-backup.json")
    args = p.parse_args(argv)
    if sys.platform != "linux":
        p.error("Linux required")
    if "cinnamon" not in os.getenv("XDG_CURRENT_DESKTOP", "").lower():
        p.error("Run from a live Cinnamon desktop session")
    if os.geteuid() == 0:
        p.error("Do not run with sudo")
    try:
        if args.restore:
            backup = json.loads(args.backup.read_text(encoding="utf-8"))
            if backup.get("format") != FORMAT or backup.get("schema") != SCHEMA or set(backup.get("values", {})) != set(KEYS):
                raise LayoutError("Invalid backup format")
            for key in KEYS:
                decode_strv(backup["values"][key])
            for key in KEYS:
                set_setting(key, backup["values"][key])
            args.backup.unlink()
            print("Original panel configuration restored")
            return 0
        original = {key: get_setting(key) for key in KEYS}
        panels, applets = build_layout(decode_strv(original[KEYS[0]]), decode_strv(original[KEYS[1]]))
        updated = {KEYS[0]: encode_strv(panels), KEYS[1]: encode_strv(applets)}
        print(json.dumps({"mode": "apply" if args.apply else "preview", "changes": updated, "backup": str(args.backup)}, indent=2))
        if not args.apply:
            print("Preview only; use --apply to save a backup and change Cinnamon settings")
            return 0
        safe_save(args.backup, {"format": FORMAT, "schema": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(), "values": original})
        try:
            for key in KEYS:
                set_setting(key, updated[key])
        except subprocess.CalledProcessError:
            for key in KEYS:
                try:
                    set_setting(key, original[key])
                except subprocess.CalledProcessError:
                    pass
            raise LayoutError("Apply failed; rollback attempted. Backup remains at " + str(args.backup))
        print("Classic panel layout applied. Revert using --restore")
        return 0
    except (LayoutError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
