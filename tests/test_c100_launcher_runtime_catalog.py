"""Targeted checks for the opt-in desktop-entry catalogue in the compiled Classic launcher.

Pure tests reuse canopy_features.launcher.launcher_catalog_ingest: the Python
contract produces the snapshot, this module serialises it to the narrow
read-only bridge format, and the compiled probe proves the C++ host model
accepts that exact snapshot and rejects hostile input (SYNTHETIC, offscreen).
No desktop, network, XDG walk, credential or visual acceptance is involved.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from canopy_features.launcher.desktop_entry_parser import DesktopEntry
from canopy_features.launcher.launcher_catalog_ingest import (
    MAX_ENTRIES,
    MAX_TITLE_CHARS,
    compose_launcher_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "prototype" / "classic"
HEADER = PROTO / "LauncherModel.h"
SOURCE = PROTO / "LauncherModel.cpp"
QML = PROTO / "LauncherOverlay.qml"
MAIN = PROTO / "main.cpp"
CMAKE = PROTO / "CMakeLists.txt"

PROBE = r'''
#include "LauncherModel.h"
#include <QCoreApplication>
#include <QDebug>
static bool check(bool ok, const char *name) {
    qInfo().noquote() << (ok ? "CATALOG_RUNTIME_PASS " : "CATALOG_RUNTIME_FAIL ")
                      << name;
    return ok;
}
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (argc < 3) return 2;
    bool ok = LauncherCatalogModel::selfTest();
    LauncherCatalogModel model;
    ok &= check(model.loadFromFile(QString::fromLocal8Bit(argv[1])), "fixture load");
    ok &= check(model.active() && model.rowCount() == 3, "fixture rows");
    const QStringList titles = model.titles();
    ok &= check(titles.size() == 3 && titles.at(0) == QStringLiteral("Files")
                && titles.at(1) == QStringLiteral("Browser")
                && titles.at(2) == QStringLiteral("Terminal"), "snapshot order");
    ok &= check(model.filter(QStringLiteral("fIlEs")).count() == 1
                && model.browse().count() == 3, "compiled search parity");
    LauncherCatalogModel hostile;
    ok &= check(!hostile.loadFromFile(QString::fromLocal8Bit(argv[2])),
                "hostile file rejected");
    ok &= check(!hostile.active() && hostile.rowCount() == 0,
                "hostile never activates");
    ok &= check(!model.loadFromFile(QString::fromLocal8Bit(argv[2]))
                && model.rowCount() == 3 && model.titles() == titles,
                "rejection retains prior snapshot");
    qInfo().noquote() << (ok ? "CATALOG_RUNTIME_ALL_PASS"
                             : "CATALOG_RUNTIME_ALL_FAIL");
    return ok ? 0 : 1;
}
'''

MARKERS = (
    "default inactive fail closed", "bounded text ingest", "snapshot order",
    "QML bridge shape", "host-side filter parity", "invalid id fails closed",
    "path-like id fails closed", "control title fails closed",
    "empty title fails closed", "rejected snapshot leaves model empty",
    "missing file fails closed", "fixture load", "fixture rows",
    "compiled search parity", "hostile file rejected", "hostile never activates",
    "rejection retains prior snapshot",
)


def entry(name):
    return DesktopEntry(
        values={"Type": "Application", "Name": name,
                "Exec": "/usr/bin/" + name.lower(), "Icon": name.lower(),
                "Categories": "Utility;"},
        localized={},
    )


def snapshot(*names):
    return compose_launcher_catalog(
        (("org.example.%s.desktop" % name.replace(" ", ""), entry(name))
         for name in names)
    )


def encode_snapshot(result):
    """Serialise the pure contract's pairs to the strict host bridge format."""
    lines = ["%s\t%s\n" % (app_id, title)
             for app_id, title in result.to_pairs()]
    return "".join(lines).encode("utf-8")


def _toolchain():
    gpp = os.environ.get("CANOPY_QT_GPP")
    if not gpp:
        for candidate in (shutil.which("g++"), "C:/msys64/ucrt64/bin/g++.exe",
                          "/usr/bin/g++"):
            if candidate and Path(candidate).is_file():
                gpp = candidate
                break
    if not gpp or not Path(gpp).is_file():
        return None
    qmake = os.environ.get("CANOPY_QT_QMAKE")
    if not qmake:
        for candidate in (shutil.which("qmake6"),
                          "C:/msys64/ucrt64/bin/qmake6.exe", "/usr/bin/qmake6"):
            if candidate and Path(candidate).is_file():
                qmake = candidate
                break
    if not qmake or not Path(qmake).is_file():
        return None

    def query(flag):
        done = subprocess.run([qmake, "-query", flag], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30, check=False)
        return done.stdout.decode("utf-8", "replace").strip()

    includes, libs = query("QT_INSTALL_HEADERS"), query("QT_INSTALL_LIBS")
    if not includes or not libs or not Path(includes).is_dir() or not Path(libs).is_dir():
        return None
    return gpp, includes, libs


class RuntimeCatalogSourceTests(unittest.TestCase):
    def test_python_contract_feeds_an_ordered_bounded_snapshot(self):
        result = snapshot("Files", "Browser", "Terminal")
        self.assertEqual(result.to_pairs(), (
            ("org.example.Files.desktop", "Files"),
            ("org.example.Browser.desktop", "Browser"),
            ("org.example.Terminal.desktop", "Terminal"),
        ))
        wire = encode_snapshot(result)
        self.assertEqual(wire.count(b"\n"), 3)
        self.assertTrue(all(b"\t" in line for line in wire.splitlines()))
        self.assertEqual(result.to_dict()["claims"], list(result.claims))

    def test_hidden_and_duplicate_entries_never_reach_the_bridge(self):
        entries = [
            ("org.example.A.desktop", entry("One")),
            ("org.example.A.desktop", entry("Ignored")),
            ("org.example.Hidden.desktop", DesktopEntry(
                values={"Type": "Application", "Name": "Hidden",
                        "Hidden": "true", "Exec": "/usr/bin/hidden"},
                localized={})),
        ]
        result = compose_launcher_catalog(entries)
        self.assertEqual(result.to_pairs(),
                         (("org.example.A.desktop", "One"),))
        self.assertEqual(result.duplicate_id_count, 1)
        self.assertEqual(result.hidden_count, 1)
        self.assertNotIn(b"Ignored", encode_snapshot(result))

    def test_bridge_format_never_carries_control_or_path_ids(self):
        result = snapshot("Files")
        self.assertEqual(MAX_ENTRIES, 1024)
        self.assertEqual(MAX_TITLE_CHARS, 256)
        wire = encode_snapshot(result)
        self.assertNotIn(b"\r", wire)
        self.assertNotIn(b"\x00", wire)
        with self.assertRaises(ValueError):
            compose_launcher_catalog(
                (("../evil.desktop", entry("Files")),))
        with self.assertRaises(ValueError):
            compose_launcher_catalog(
                (("org.example.Files.desktop", entry("Fi\x01les")),))

    def test_bounded_readonly_model_source_contract(self):
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        for needle in ("static constexpr int MaxSnapshotBytes = 64 * 1024",
                       "static constexpr int MaxRows = 1024",
                       "static constexpr int MaxTitleChars = 256",
                       "bool loadFromFile(const QString &path)",
                       "bool loadFromText(const QString &text)",
                       "QVariantList applications() const"):
            self.assertIn(needle, header, needle)
        for needle in ("QFile file(path)", "QIODevice::ReadOnly",
                       "QStringDecoder", "seenIds.contains(appId)"):
            self.assertIn(needle, source, needle)
        for forbidden in ("QProcess", "QTcpSocket", "QNetwork", "QDirIterator",
                          "QDesktopServices", "system(", "popen("):
            self.assertNotIn(forbidden, source, forbidden)
            self.assertNotIn(forbidden, header, forbidden)

    def test_qml_bridge_is_guarded_and_approved_order_is_preserved(self):
        qml = QML.read_text(encoding="utf-8")
        doc = (ROOT / "docs" / "CLASSIC_LAUNCHER_RUNTIME_CATALOG.md").read_text(
            encoding="utf-8")
        self.assertIn("typeof canopyLauncherCatalog", qml)
        self.assertIn("canopyLauncherCatalog.active", qml)
        self.assertIn("canopyLauncherCatalog.applications()", qml)
        self.assertIn('{ title: "Browser" }, { title: "Mail" },', qml)
        self.assertIn('{ title: "Files" }, { title: "Browser" },', qml)
        # main.cpp/CMakeLists.txt are owner-locked: the exact integration
        # fragment must live in the doc, not in this PR's diff.
        self.assertIn("BLOCKED", doc)
        self.assertIn("class LauncherCatalogBridge", doc)
        self.assertIn('"--launcher-catalog"', doc)
        self.assertIn("qt_add_executable(canopy-classic-spike main.cpp "
                      "LauncherModel.cpp", doc)


@unittest.skipUnless(_toolchain(), "Qt 6 C++ toolchain not available")
class RuntimeCatalogCompiledTests(unittest.TestCase):
    """Real compile/run probe; skipped only when Qt 6 C++ is absent."""

    def test_compiled_model_consumes_python_snapshot_and_fails_closed(self):
        tool = _toolchain()
        self.assertIsNotNone(tool)
        gpp, includes, libs = tool
        with tempfile.TemporaryDirectory(prefix="canopy-runtime-catalog-") as folder:
            work = Path(folder)
            probe = work / "probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            fixture = work / "catalog.tsv"
            fixture.write_bytes(encode_snapshot(snapshot("Files", "Browser", "Terminal")))
            hostile = work / "hostile.tsv"
            hostile.write_bytes(b"../escape.desktop\tFiles\n")
            binary = work / "probe.exe"
            include_args = ["-I" + includes, "-I" + str(Path(includes) / "QtCore"),
                            "-I" + str(PROTO)]
            command = [gpp, "-std=c++17", "-fPIC", *include_args, str(probe),
                       str(SOURCE), "-L" + libs, "-lQt6Core", "-o", str(binary)]

            compile_env = os.environ.copy()
            # cc1plus.exe resolves libisl-23.dll from UCRT64/bin on
            # Windows. g++ may be found by absolute path while that DLL
            # is missing from PATH, producing rc=1 with empty output.
            # Give the compiler the same supported PATH as the probe run.
            compile_env["PATH"] = (
                "C:/msys64/ucrt64/bin" + os.pathsep
                + compile_env.get("PATH", ""))

            def compile_once():
                return subprocess.run(command, cwd=str(work), stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=180, check=False,
                                      env=compile_env)

            built = compile_once()
            if built.returncode != 0 and not built.stdout.strip():
                time.sleep(2)
                built = compile_once()
            if built.returncode != 0:
                self.fail("compiled catalogue probe failed:\n"
                          + built.stdout.decode("utf-8", "replace")[-4000:])
            env = compile_env.copy()
            env["PATH"] = "C:/msys64/ucrt64/bin" + os.pathsep + env.get("PATH", "")
            env["QT_FORCE_STDERR_LOGGING"] = "1"
            env.pop("DISPLAY", None)
            run = subprocess.run([str(binary), str(fixture), str(hostile)], env=env,
                                 cwd=str(work), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=60, check=False)
            output = run.stdout.decode("utf-8", "replace")
            self.assertEqual(run.returncode, 0, output[-4000:])
            self.assertIn("CATALOG_ALL_PASS", output)
            self.assertIn("CATALOG_RUNTIME_ALL_PASS", output)
            seen = {line.split(" ", 1)[1].strip()
                    for line in output.splitlines()
                    if line.startswith(("CATALOG_PASS ", "CATALOG_RUNTIME_PASS "))}
            for marker in MARKERS:
                self.assertIn(marker, seen, marker + "\n" + output[-2000:])


if __name__ == "__main__":
    unittest.main()
