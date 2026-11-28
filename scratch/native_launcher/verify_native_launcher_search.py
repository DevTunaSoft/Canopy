"""Deterministic SYNTHETIC checks for the M3 native launcher search contract.

Run from any cwd:  python <this file>
The report is written next to this script as synthetic_verify_report.json.
No desktop, VM, network, process launch or repository state is involved.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from typing import Any, cast

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from canopy_features.launcher.app_search_ranking import (  # noqa: E402
    ALL, EXACT, FUZZY, PREFIX, SUBSTRING,
)
from canopy_features.launcher.app_search_casefold import MAX_QUERY_CHARS  # noqa: E402
from canopy_features.launcher.native_catalog_producer import (  # noqa: E402
    MAX_SNAPSHOT_BYTES,
    produce_catalog_bytes,
)
from canopy_features.launcher.native_launcher_search import (  # noqa: E402
    FIXED_CLAIMS,
    MAX_RESULTS,
    NativeSearchError,
    search_native_catalog_bytes,
    search_native_directory,
)

MODULE = ROOT / "canopy_features" / "launcher" / "native_launcher_search.py"


def wire(*pairs):
    return "".join("%s\t%s\n" % pair for pair in pairs).encode("utf-8")


def desktop(name, *, hidden=False, no_display=False, app_id=None):
    ident = app_id or ("org.example.%s.desktop" % name.replace(" ", ""))
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=" + name,
        "Exec=/usr/bin/" + name.lower().replace(" ", "-"),
        "Categories=Utility;",
    ]
    if hidden:
        lines.append("Hidden=true")
    if no_display:
        lines.append("NoDisplay=true")
    return ident, ("\n".join(lines) + "\n").encode("utf-8")


class NativeSearchContractTests(unittest.TestCase):
    def test_ranking_tiers_are_total_and_deterministic(self):
        data = wire(
            ("org.example.zbrowser.desktop", "Web Browser"),
            ("org.example.term.desktop", "Terminal"),
            ("org.example.term2.desktop", "Terminal"),
            ("org.example.notes.desktop", "Notes"),
        )
        first = search_native_catalog_bytes(data, "term")
        second = search_native_catalog_bytes(data, "term")
        self.assertEqual(first, second)
        self.assertEqual([r.app_id for r in first], [
            "org.example.term.desktop", "org.example.term2.desktop"])
        self.assertEqual([r.tier for r in first], [PREFIX, PREFIX])
        self.assertEqual([r.score for r in first], [3, 3])
        self.assertEqual([r.index for r in first], [1, 2])
        exact = search_native_catalog_bytes(data, "terminal")
        self.assertEqual([r.tier for r in exact], [EXACT, EXACT])
        self.assertEqual([r.score for r in exact], [4, 4])
        self.assertEqual(search_native_catalog_bytes(data, "Te")[0].tier,
                         PREFIX)
        self.assertEqual(search_native_catalog_bytes(data, "brow")[0].tier,
                         SUBSTRING)
        self.assertEqual(search_native_catalog_bytes(data, "Wbro")[0].tier,
                         FUZZY)
        self.assertEqual([r.tier for r in search_native_catalog_bytes(data, "  ")],
                         [ALL, ALL, ALL, ALL])

    def test_results_are_bounded_and_immutable(self):
        pairs = [("org.example.app%03d.desktop" % i, "App %03d" % i)
                 for i in range(200)]
        results = search_native_catalog_bytes(wire(*pairs), "App", limit=7)
        self.assertEqual(len(results), 7)
        self.assertIsInstance(results, tuple)
        self.assertEqual(len(set(r.index for r in results)), 7)
        with self.assertRaises(NativeSearchError):
            search_native_catalog_bytes(wire(*pairs), "App", limit=MAX_RESULTS + 1)

    def test_limit_and_query_types_fail_closed(self):
        call = cast(Any, search_native_catalog_bytes)
        data = wire(("org.example.a.desktop", "Alpha"))
        for bad in (True, False, 0, -1, 65, 1.0, "2", None, (2,)):
            with self.assertRaises(NativeSearchError):
                call(data, "a", limit=bad)
        for bad in (None, b"a", 7, ["a"], "a" * (MAX_QUERY_CHARS + 1),
                    "bad\ud800"):
            with self.assertRaises(NativeSearchError):
                call(data, bad)

    def test_wire_shape_fail_closed(self):
        good = wire(("org.example.a.desktop", "Alpha"))
        bad_wires = (
            b"",
            good[:-1],
            good + b"extra",
            good.replace(b"\n", b"\r\n"),
            b"../evil.desktop\tAlpha\n",
            b"no-tab\n",
            b"two\ttabs\there\n",
            b"org.example.a.desktop\t\n",
            good.replace(b"Alpha", b"Al\x01pha"),
            b"\xff\xfe\tAlpha\n",
        )
        for bad in bad_wires:
            with self.assertRaises(NativeSearchError):
                search_native_catalog_bytes(bad, "a")
        with self.assertRaises(NativeSearchError):
            search_native_catalog_bytes(bytearray(good), "a")
        with self.assertRaises(NativeSearchError):
            search_native_catalog_bytes(b"x" * (MAX_SNAPSHOT_BYTES + 1), "a")
        oversized = wire(*[("org.example.a%03d.desktop" % i, "A") for i in range(1025)])
        with self.assertRaises(NativeSearchError):
            search_native_catalog_bytes(oversized, "a")

    def test_directory_entry_point_reuses_the_single_producer(self):
        with tempfile.TemporaryDirectory(prefix="m3-launcher-") as folder:
            root = Path(folder) / "applications"
            root.mkdir()
            for name, data in (desktop("Konsole"), desktop("Dolphin"),
                               desktop("Kate"), desktop("Hidden", hidden=True),
                               desktop("NoShow", no_display=True)):
                (root / name).write_bytes(data)
            results = search_native_directory(str(root), "dol")
            self.assertEqual([r.app_id for r in results],
                             ["org.example.Dolphin.desktop"])
            self.assertEqual(results[0].title, "Dolphin")
            wire_bytes = produce_catalog_bytes(str(root))
            self.assertEqual(search_native_catalog_bytes(wire_bytes, "dol"), results)
            with self.assertRaises(NativeSearchError):
                search_native_directory(str(root.parent / "missing"), "dol")

    def test_fixed_claims_are_true_by_construction(self):
        import ast
        source = MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports, calls = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        allowed_imports = {
            "__future__", "dataclasses", "unicodedata", "typing",
            "canopy_features.apps.launch_argv",
            "canopy_features.launcher.app_search_casefold",
            "canopy_features.launcher.app_search_ranking",
            "canopy_features.launcher.launcher_catalog_ingest",
            "canopy_features.launcher.native_catalog_producer",
        }
        self.assertLessEqual(imports, allowed_imports)
        for forbidden_call in ("Popen", "system", "sleep", "connect", "get",
                               "post", "request", "launch", "start", "open",
                               "spawn", "fork", "thread"):
            self.assertNotIn(forbidden_call, calls, forbidden_call)
        for token in FIXED_CLAIMS:
            self.assertIn(token, source)
        self.assertEqual(source.count("produce_catalog_bytes"), 3,
                         "docstring reference, one import, one call; "
                         "no second catalog reader")
        self.assertEqual(MAX_RESULTS, 64)
        self.assertEqual(MAX_QUERY_CHARS, 128)

    def test_upstream_caps_are_not_widened(self):
        from canopy_features.launcher.launcher_catalog_ingest import MAX_ENTRIES
        from canopy_features.launcher.launcher_catalog_ingest import MAX_TITLE_CHARS
        self.assertEqual(MAX_ENTRIES, 1024)
        self.assertEqual(MAX_TITLE_CHARS, 256)
        self.assertLessEqual(MAX_RESULTS, MAX_ENTRIES)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeSearchContractTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = {
        "classification": "SYNTHETIC",
        "module": str(MODULE),
        "module_sha256": sha256(MODULE),
        "script_sha256": sha256(Path(__file__)),
        "tests_run": result.testsRun,
        "failures": [str(test) for test, _ in result.failures],
        "errors": [str(test) for test, _ in result.errors],
        "verdict": "PASS" if result.wasSuccessful() else "FAIL",
        "log": stream.getvalue(),
    }
    out = HERE / "synthetic_verify_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(stream.getvalue(), end="")
    print("VERDICT=%s tests=%d failures=%d errors=%d report=%s" % (
        report["verdict"], report["tests_run"], len(report["failures"]),
        len(report["errors"]), out))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
