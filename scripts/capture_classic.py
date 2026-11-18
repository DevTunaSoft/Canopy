"""Capture only Canopy preview windows in a disposable Xvfb test display.

This tool does not interact with a live Cinnamon session, capture the entire
desktop, or grant remote control. The caller must supply an isolated Xvfb DISPLAY.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone


def _require_test_display(environment):
    """A lightweight intent guard, not a security sandbox."""
    display = environment.get("DISPLAY", "")
    if environment.get("CANOPY_ISOLATED_DISPLAY") != "1" or not display.startswith(":"):
        raise ValueError("Use an isolated Xvfb display with CANOPY_ISOLATED_DISPLAY=1")
    if environment.get("WAYLAND_DISPLAY"):
        raise ValueError("Wayland desktop screenshot capture is not supported")


def _capture_windows(Gtk, Gdk, output_dir):
    """Save bounded screenshots of the two Canopy preview windows only."""
    windows = [
        window for window in Gtk.Window.list_toplevels()
        if window.get_title() == "Canopy Classic preview" and window.get_mapped()
    ]
    if len(windows) != 2:
        raise RuntimeError(f"Expected 2 visible Canopy windows, found {len(windows)}")

    captures = []
    for window in windows:
        classes = window.get_child().get_style_context()
        role = ("top-bar" if classes.has_class("canopy-panel") else
                "dock" if classes.has_class("canopy-dock") else None)
        if role is None:
            raise RuntimeError("Unexpected Canopy preview window")
        width, height = window.get_size()
        if not 0 < width <= 8192 or not 0 < height <= 8192:
            raise RuntimeError(f"Invalid {role} dimensions: {width}x{height}")
        gdk_window = window.get_window()
        if gdk_window is None:
            raise RuntimeError(f"No drawable surface for {role}")
        pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, width, height)
        if pixbuf is None:
            raise RuntimeError(f"Could not capture {role}")
        path = output_dir / f"{role}.png"
        if not pixbuf.savev(str(path), "png", [], []):
            raise RuntimeError(f"Could not save {role}")
        captures.append({"role": role, "filename": path.name,
                         "width": width, "height": height})
    if {entry["role"] for entry in captures} != {"top-bar", "dock"}:
        raise RuntimeError("Missing a preview window type")
    return sorted(captures, key=lambda entry: entry["role"])


def capture(output_dir, *, environment=None):
    env = os.environ if environment is None else environment
    _require_test_display(env)
    if os.geteuid() == 0:
        raise ValueError("Run graphical tests as an unprivileged user")

    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk
    from canopy.classic_gtk import run

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    images = []

    def take_snapshot():
        try:
            images.extend(_capture_windows(Gtk, Gdk, output_dir))
        except Exception as error:
            errors.append(str(error))
        finally:
            Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    source = GLib.timeout_add(1600, take_snapshot)
    try:
        run(safe_defaults=True)
    finally:
        if not images and not errors:
            GLib.source_remove(source)
    if errors:
        raise RuntimeError("; ".join(errors))
    if len(images) != 2:
        raise RuntimeError("Preview exited without two window captures")
    report = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "isolated-xvfb",
        "status": "PASS",
        "captures": images,
    }
    (output_dir / "captures.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Capture Canopy-only GTK test windows")
    parser.add_argument("--output-dir", type=Path, default=Path("test-results/visual"))
    args = parser.parse_args(argv)
    try:
        report = capture(args.output_dir)
    except (ValueError, RuntimeError, ImportError, OSError) as error:
        print(f"Capture failed: {error}", file=sys.stderr)
        return 1
    print(f"Captured {len(report['captures'])} Canopy windows: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
