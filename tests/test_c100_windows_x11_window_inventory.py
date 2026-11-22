"""Offline unit tests for read-only X11 inventory normalization.

No real X server, Mint session, Qt build or compiled application is used here.
"""
import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.windows.x11_window_inventory import (
    MAX_LINE_BYTES, MAX_WINDOWS, RawInventory, Window, collect,
    normalize_inventory,
)


class FixtureAdapter:
    """Caller-owned read-only source; no process, socket or display access."""

    def __init__(self, lines=(), *, available=True, error=None):
        self.lines = list(lines)
        self.available = available
        self.error = error
        self.calls = 0

    def read_inventory(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return RawInventory(tuple(self.lines), self.available)


class NormalizeTests(unittest.TestCase):
    def test_canonical_ids_desktops_and_titles(self):
        lines = (
            "0X2a 0 host Alpha\tBeta",
            "0x00000003 -1 host  Sticky   window  ",
            "0x0000000a 65535 host Term",
        )
        result = normalize_inventory(lines)
        self.assertEqual(result.status, "OK")
        self.assertTrue(result.available)
        self.assertEqual(result.rejected_lines, 0)
        self.assertFalse(result.truncated)
        self.assertEqual(result.ids, ("0x00000003", "0x0000000a", "0x0000002a"))
        self.assertEqual(
            result.windows,
            (Window("0x00000003", -1, "Sticky window"),
             Window("0x0000000a", 65535, "Term"),
             Window("0x0000002a", 0, "Alpha Beta")),
        )

    def test_malformed_ids_and_fields_are_counted_not_raised(self):
        bad_lines = [
            "0xZZ 0 host Bad id",
            "0x 0 host Empty id",
            "12345 0 host Decimal id",
            "0x1234567890abcdef0 0 host Too many digits",
            "0x1g 0 host Trailer",
            "0x1 0 host",
            "0x1 nope host Bad desktop",
            "0x1 -2 host Negative desktop",
            "0x1 70000 host Oversized desktop",
            "0x1 0 host " + "x" * MAX_LINE_BYTES,
            b"0x1 0 host Bytes",
            "0x1 0 host \ud800",
        ]
        for line in bad_lines:
            with self.subTest(line=repr(line)[:40]):
                result = normalize_inventory((line,))
                self.assertEqual(result.windows, ())
                self.assertEqual(result.rejected_lines, 1)
                self.assertEqual(result.status, "OK")
        self.assertTrue(normalize_inventory(tuple(bad_lines)).available)

    def test_duplicate_ids_keep_first_and_bounds_are_enforced(self):
        result = normalize_inventory(
            ("0x00000001 0 host First", "0X1 0 host Duplicate"),
            max_windows=2,
        )
        self.assertEqual(result.windows, (Window("0x00000001", 0, "First"),))
        self.assertEqual(result.rejected_lines, 1)

        many = tuple(f"0x{i:x} 0 host W{i}" for i in range(1, 20))
        capped = normalize_inventory(many, max_windows=2)
        self.assertEqual(len(capped.windows), 2)
        self.assertTrue(capped.truncated)
        self.assertEqual(capped.windows[0].window_id, "0x00000001")
        self.assertEqual(capped.windows[1].window_id, "0x00000002")

        scanned = normalize_inventory(("0xzz 0 host bad",) * 20,
                                      max_windows=2)
        self.assertTrue(scanned.truncated)
        self.assertEqual(scanned.rejected_lines, 8)  # scan limit = 4 * bound

    def test_stale_windows_follow_previous_ids(self):
        adapter = FixtureAdapter(("0x1 0 host One", "0x2 0 host Two"))
        first = collect(adapter)
        self.assertEqual(first.ids, ("0x00000001", "0x00000002"))
        self.assertEqual(first.stale_ids, ())

        adapter.lines = ["0x00000001 0 host One"]
        second = collect(adapter, known_ids=first.ids)
        self.assertEqual(second.ids, ("0x00000001",))
        self.assertEqual(second.stale_ids, ("0x00000002",))

        third = collect(adapter, known_ids=second.ids)
        self.assertEqual(third.stale_ids, ())
        self.assertEqual(adapter.calls, 3)

    def test_invalid_known_ids_are_ignored(self):
        result = normalize_inventory(
            ("0x1 0 host One",),
            known_ids=[True, "0xzz", "0X00000002", 3, None, "0x00000001"],
        )
        self.assertEqual(result.ids, ("0x00000001",))
        self.assertEqual(result.stale_ids,
                         ("0x00000002", "0x00000003"))
        with self.assertRaises(TypeError):
            normalize_inventory((), known_ids="0x1")


class AdapterTests(unittest.TestCase):
    def test_missing_adapter_and_unavailable_display(self):
        known = ["0x00000001"]
        missing = collect(None, known_ids=known)
        self.assertEqual(missing.status, "NO_ADAPTER")
        self.assertFalse(missing.available)
        self.assertEqual(missing.windows, ())
        self.assertEqual(missing.stale_ids, ("0x00000001",))

        adapter = FixtureAdapter(("0x1 0 host One",), available=False)
        unavailable = collect(adapter, known_ids=known)
        self.assertEqual(unavailable.status, "DISPLAY_UNAVAILABLE")
        self.assertFalse(unavailable.available)
        self.assertEqual(unavailable.windows, ())
        self.assertEqual(unavailable.rejected_lines, 0)
        self.assertEqual(unavailable.stale_ids, ("0x00000001",))
        self.assertEqual(adapter.calls, 1)

    def test_adapter_failure_and_bad_shape_do_not_leak_details(self):
        secret = "DISPLAY=:0 PASSWORD=hunter2"
        broken = FixtureAdapter(error=OSError(secret))
        for adapter in (broken, object(),
                        FixtureAdapter(error=OSError(secret))):
            with self.subTest(adapter=type(adapter).__name__):
                result = collect(adapter)
                self.assertIn(result.status, ("ADAPTER_ERROR", "INVALID_ADAPTER"))
                self.assertFalse(result.available)
                self.assertEqual(result.windows, ())
                self.assertNotIn("hunter2", repr(result))
        self.assertEqual(broken.calls, 1)

        class WrongReturn:
            def read_inventory(self):
                return ("0x1 0 host One",)

        class BadLines:
            def read_inventory(self):
                return RawInventory("0x1 0 host One", True)

        self.assertEqual(collect(WrongReturn()).status, "INVALID_ADAPTER")
        self.assertEqual(collect(BadLines()).status, "INVALID_ADAPTER")

    def test_snapshot_is_immutable_and_source_is_not_mutated(self):
        lines = ["0x1 0 host One"]
        adapter = FixtureAdapter(lines)
        result = collect(adapter)
        self.assertEqual(adapter.lines, lines)
        self.assertIsInstance(result.windows, tuple)
        self.assertIsInstance(result.ids, tuple)
        with self.assertRaises(FrozenInstanceError):
            result.status = "OK"
        with self.assertRaises(FrozenInstanceError):
            result.windows[0].title = "changed"

    def test_bad_bounds_and_line_types_are_rejected(self):
        for bound in (0, -1, MAX_WINDOWS + 1, True, "2"):
            with self.subTest(bound=bound):
                with self.assertRaises(ValueError):
                    normalize_inventory((), max_windows=bound)
        for size in (0, MAX_LINE_BYTES + 1, False):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    normalize_inventory((), max_line_bytes=size)
        with self.assertRaises(TypeError):
            normalize_inventory(None)
        with self.assertRaises(TypeError):
            normalize_inventory(iter(("0x1 0 host One",)))


class SourceGuardTests(unittest.TestCase):
    def test_no_process_polling_network_or_filesystem_calls(self):
        path = Path(__file__).resolve().parents[1] / \
            "canopy_features/windows/x11_window_inventory.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        forbidden_calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    forbidden_calls.add(function.id)
                elif isinstance(function, ast.Attribute):
                    forbidden_calls.add(function.attr)
        self.assertTrue(imports.issubset({"dataclasses", "re", "typing"}))
        self.assertFalse({"subprocess", "socket", "open", "sleep", "Popen",
                          "run", "connect", "request"} & forbidden_calls)
        self.assertFalse(any(isinstance(node, ast.While) for node in ast.walk(tree)))


if __name__ == "__main__":
    unittest.main()
