"""Tests for isolated screenshot boundaries, without requiring GTK locally."""
from pathlib import Path
import tempfile
import unittest

from scripts.capture_classic import _capture_windows, _require_test_display


class DisplayGuardTests(unittest.TestCase):
    def test_requires_explicit_isolated_display(self):
        for env in ({}, {"DISPLAY": ":7"},
                    {"CANOPY_ISOLATED_DISPLAY": "1", "DISPLAY": "wayland-0"},
                    {"CANOPY_ISOLATED_DISPLAY": "1", "DISPLAY": ":7",
                     "WAYLAND_DISPLAY": "wayland-0"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                _require_test_display(env)

    def test_allows_explicit_virtual_x11_display(self):
        _require_test_display({"DISPLAY": ":7", "CANOPY_ISOLATED_DISPLAY": "1"})


class FakeStyle:
    def __init__(self, css): self.css = css
    def has_class(self, name): return self.css == name


class FakeBox:
    def __init__(self, css): self.css = css
    def get_style_context(self): return FakeStyle(self.css)


class FakePixbuf:
    def __init__(self): self.calls = []
    def savev(self, path, file_format, *_args):
        self.calls.append((path, file_format))
        Path(path).write_bytes(b"PNG placeholder for model test")
        return True


class FakeWindow:
    def __init__(self, css, title="Canopy Classic preview", mapped=True, size=(200, 40)):
        self.css, self.title, self.mapped, self.size = css, title, mapped, size
    def get_title(self): return self.title
    def get_mapped(self): return self.mapped
    def get_child(self): return FakeBox(self.css)
    def get_size(self): return self.size
    def get_window(self): return self


class FakeGtk:
    class Window:
        all_windows = []
        @classmethod
        def list_toplevels(cls): return cls.all_windows


class FakeGdk:
    captured = []
    @classmethod
    def pixbuf_get_from_window(cls, window, x, y, width, height):
        cls.captured.append((window.css, x, y, width, height))
        return FakePixbuf()


class ScreenshotTests(unittest.TestCase):
    def test_captures_only_expected_named_windows(self):
        FakeGtk.Window.all_windows = [
            FakeWindow("canopy-panel"),
            FakeWindow("canopy-dock"),
            FakeWindow("canopy-panel", title="Personal email"),
            FakeWindow("canopy-panel", mapped=False),
        ]
        FakeGdk.captured = []
        with tempfile.TemporaryDirectory() as directory:
            captures = _capture_windows(FakeGtk, FakeGdk, Path(directory))
            self.assertEqual([item["role"] for item in captures], ["dock", "top-bar"])
            self.assertEqual(sorted(p.name for p in Path(directory).glob("*.png")),
                             ["dock.png", "top-bar.png"])
            self.assertEqual(len(FakeGdk.captured), 2)

    def test_refuses_unexpected_and_invalid_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            for windows in ([], [FakeWindow("canopy-panel")],
                            [FakeWindow("canopy-panel"), FakeWindow("other")],
                            [FakeWindow("canopy-panel", size=(0, 20)), FakeWindow("canopy-dock")]):
                FakeGtk.Window.all_windows = windows
                with self.subTest(windows=len(windows)), self.assertRaises(RuntimeError):
                    _capture_windows(FakeGtk, FakeGdk, Path(directory))


if __name__ == "__main__":
    unittest.main()
