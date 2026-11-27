"""ND-038 compiled launcher catalog refresh / enumeration contract gate.

The merged Python contracts are event-driven and bounded. This module proves
that the compiled launcher *model* exposes an equivalent, fail-closed adapter:
one bounded producer call per trusted ``app.catalog.changed`` event, no timer,
no polling, atomic refusal on malformed input, and a deterministic enumeration
source mirror. It is SYNTHETIC: a real g++/Qt6 probe run offscreen with
in-memory wires; no desktop, Mint guest, visual or release acceptance is
claimed. The host-event call site itself remains blocked in main.cpp, which
this task does not own; see the PR body for the exact blocker.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "prototype" / "classic"
HEADER = PROTO / "LauncherModel.h"
SOURCE = PROTO / "LauncherModel.cpp"

PROBE = r'''
#include "LauncherModel.h"
#include <QCoreApplication>
#include <QDebug>

static bool check(bool ok, const char *name) {
    qInfo().noquote() << (ok ? "ND038_PASS " : "ND038_FAIL ") << name;
    return ok;
}

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    bool ok = true;
    LauncherCatalogModel model;
    ok &= check(model.loadFromText(
                    QStringLiteral("org.example.One.desktop\tOne\n")),
                "initial installed-app display");

    int calls = 0;
    QString wire = QStringLiteral("org.example.One.desktop\tOne\n"
                                  "org.example.Two.desktop\tTwo\n");
    LauncherCatalogRefresh refresh(
        model, QStringLiteral("host-events"),
        [&calls, &wire](QString *out) { ++calls; *out = wire; return true; });
    QVariantMap event;
    event.insert(QStringLiteral("source"), QStringLiteral("host-events"));
    event.insert(QStringLiteral("sequence"), 1);

    ok &= check(refresh.applyHostEvent(
                    QStringLiteral("app.catalog.changed"), event)
                    && calls == 1 && model.rowCount() == 2
                    && refresh.lastReport().installedCount == 1
                    && refresh.lastReport().producerCalls == 1,
                "one bounded producer call per trusted event");
    ok &= check(LauncherCatalogRefresh::outcomeToken(
                    refresh.lastReport().outcome) == QStringLiteral("refreshed"),
                "fixed refreshed token");

    ok &= check(!refresh.applyHostEvent(
                    QStringLiteral("app.catalog.changed"), event)
                    && calls == 1 && refresh.producerCalls() == 1,
                "replayed sequence rejected without producer call");
    event.insert(QStringLiteral("sequence"), 1);
    QVariantMap wrongSource = event;
    wrongSource.insert(QStringLiteral("source"), QStringLiteral("untrusted"));
    ok &= check(!refresh.applyHostEvent(
                    QStringLiteral("app.catalog.changed"), wrongSource)
                    && calls == 1,
                "untrusted source rejected");
    ok &= check(!refresh.applyHostEvent(
                    QStringLiteral("wifi.scan.changed"), event) && calls == 1,
                "unlisted topic rejected");

    event.insert(QStringLiteral("sequence"), 2);
    wire = QStringLiteral("org.example.One.desktop\tOne\n"
                          "org.example.Three.desktop\tThree\n"
                          "bad id\tFour\n");
    ok &= check(!refresh.applyHostEvent(
                    QStringLiteral("app.catalog.changed"), event)
                    && calls == 2
                    && LauncherCatalogRefresh::outcomeToken(
                           refresh.lastReport().outcome)
                           == QStringLiteral("snapshot_refused")
                    && model.rowCount() == 2
                    && model.titles().at(1) == QStringLiteral("Two"),
                "malformed entry refuses atomically and preserves display");

    event.insert(QStringLiteral("sequence"), 3);
    wire = QStringLiteral("org.example.One.desktop\tOne\n"
                          "org.example.Two.desktop\tTwo\n");
    ok &= check(refresh.applyHostEvent(
                    QStringLiteral("app.catalog.changed"), event)
                    && calls == 3
                    && LauncherCatalogRefresh::outcomeToken(
                           refresh.lastReport().outcome)
                           == QStringLiteral("unchanged"),
                "identical wire reports unchanged");

    bool budgetClean = true;
    for (int sequence = 4; sequence <= 64; ++sequence) {
        event.insert(QStringLiteral("sequence"), sequence);
        if (!refresh.applyHostEvent(QStringLiteral("app.catalog.changed"), event))
            budgetClean = false;
    }
    ok &= check(budgetClean && calls == 64 && refresh.eventCount() == 64,
                "bounded budget accepted event");
    event.insert(QStringLiteral("sequence"), 65);
    ok &= check(!refresh.applyHostEvent(
                    QStringLiteral("app.catalog.changed"), event)
                    && calls == 64 && !refresh.connected()
                    && LauncherCatalogRefresh::outcomeToken(
                           refresh.lastReport().outcome)
                           == QStringLiteral("refresh_limit")
                    && refresh.lastReport().producerCalls == 0,
                "refresh budget freezes without producer call");
    ok &= check(LauncherCatalogRefresh::validSourceIdentity(
                    QStringLiteral("host-events"))
                    && !LauncherCatalogRefresh::validSourceIdentity(
                           QStringLiteral("host events!")),
                "source identity allowlist");

    using Source = LauncherEnumerationSources::Source;
    QVector<Source> sources = {
        {LauncherEnumerationSources::Role::Explicit, QStringLiteral("C:/apps"), 128},
        {LauncherEnumerationSources::Role::XdgDataDirs,
         QStringLiteral("/usr/share/applications"), 512},
    };
    LauncherEnumerationSources::Snapshot snapshot;
    ok &= check(LauncherEnumerationSources::describe(sources, &snapshot)
                    && snapshot.sources.size() == 2
                    && snapshot.totalEntries == 640
                    && snapshot.sources.at(0).role
                           == LauncherEnumerationSources::Role::Explicit
                    && snapshot.sources.at(1).role
                           == LauncherEnumerationSources::Role::XdgDataDirs
                    && snapshot.claims().size() == 8,
                "enumeration sources normalised and bounded");

    QVector<Source> nine;
    for (int i = 0; i < 9; ++i)
        nine.append({LauncherEnumerationSources::Role::Explicit,
                     QStringLiteral("/apps/%1").arg(i), 1});
    ok &= check(!LauncherEnumerationSources::describe(nine, &snapshot),
                "source count ceiling");
    QVector<Source> traversal = {
        {LauncherEnumerationSources::Role::Explicit,
         QStringLiteral("/usr/../etc/applications"), 1}};
    ok &= check(!LauncherEnumerationSources::describe(traversal, &snapshot),
                "traversal path refused");
    QVector<Source> duplicate = {
        {LauncherEnumerationSources::Role::Explicit, QStringLiteral("/apps"), 1},
        {LauncherEnumerationSources::Role::Explicit, QStringLiteral("/apps"), 1}};
    ok &= check(!LauncherEnumerationSources::describe(duplicate, &snapshot),
                "duplicate source refused");
    QVector<Source> oversized = {
        {LauncherEnumerationSources::Role::Explicit, QStringLiteral("/apps"), 513}};
    ok &= check(!LauncherEnumerationSources::describe(oversized, &snapshot),
                "per-source cap ceiling");
    QVector<Source> totalExceeded = {
        {LauncherEnumerationSources::Role::Explicit, QStringLiteral("/a"), 512},
        {LauncherEnumerationSources::Role::XdgDataHome, QStringLiteral("/b"), 512},
        {LauncherEnumerationSources::Role::XdgDataDirs, QStringLiteral("/c"), 1}};
    ok &= check(!LauncherEnumerationSources::describe(totalExceeded, &snapshot),
                "total entry ceiling");

    qInfo().noquote() << (ok ? "ND038_ALL_PASS" : "ND038_ALL_FAIL");
    return ok ? 0 : 1;
}
'''

MARKERS = (
    "initial installed-app display",
    "one bounded producer call per trusted event",
    "fixed refreshed token",
    "replayed sequence rejected without producer call",
    "untrusted source rejected",
    "unlisted topic rejected",
    "malformed entry refuses atomically and preserves display",
    "identical wire reports unchanged",
    "bounded budget accepted event",
    "refresh budget freezes without producer call",
    "source identity allowlist",
    "enumeration sources normalised and bounded",
    "source count ceiling",
    "traversal path refused",
    "duplicate source refused",
    "per-source cap ceiling",
    "total entry ceiling",
)


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


class Nd038SourceContractTests(unittest.TestCase):
    def test_merged_python_contracts_are_present_and_bounded(self):
        refresh = (ROOT / "canopy_features" / "catalog"
                   / "native_catalog_refresh.py").read_text(encoding="utf-8")
        sources = (ROOT / "canopy_features" / "launcher"
                   / "launcher_enumeration_sources.py").read_text(encoding="utf-8")
        for token in ("REFRESH_TOPIC = \"app.catalog.changed\"",
                      "MAX_REFRESH_EVENTS = 64", "CLAIM_NO_TIMER"):
            self.assertIn(token, refresh, token)
        for token in ("MAX_SOURCES = 8", "MAX_PATH_CHARS = 512",
                      "MAX_ENTRIES_PER_SOURCE = 512",
                      "MAX_TOTAL_ENTRIES = 1024"):
            self.assertIn(token, sources, token)

    def test_compiled_model_has_no_polling_or_process_path(self):
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("QTimer", "sleep(", "QProcess", "QTcpSocket",
                          "QDirIterator", "std::thread", "while (true)"):
            self.assertNotIn(forbidden, header, forbidden)
            self.assertNotIn(forbidden, source, forbidden)
        self.assertIn("app.catalog.changed", source)
        self.assertIn("bool applyHostEvent(const QString &topic, "
                      "const QVariantMap &payload);", header)
        # The existing single-load host bridge in main.cpp stays untouched.
        main = (PROTO / "main.cpp").read_text(encoding="utf-8")
        self.assertEqual(main.count("launcherCatalog.loadFromFile("), 1)


@unittest.skipUnless(_toolchain(), "Qt 6 C++ toolchain not available")
class Nd038CompiledTests(unittest.TestCase):
    def test_compiled_refresh_and_enumeration_contract(self):
        tool = _toolchain()
        if tool is None:
            self.skipTest("Qt 6 C++ toolchain not available")
        gpp, includes, libs = tool
        with tempfile.TemporaryDirectory(prefix="nd038-catalog-refresh-") as folder:
            work = Path(folder)
            probe = work / "probe.cpp"
            probe.write_text(PROBE, encoding="utf-8")
            binary = work / "probe.exe"
            env = os.environ.copy()
            env["PATH"] = "C:/msys64/ucrt64/bin" + os.pathsep + env.get("PATH", "")
            args = [gpp, "-std=c++17", "-fPIC", "-I" + includes,
                    "-I" + str(Path(includes) / "QtCore"), "-I" + str(PROTO),
                    str(probe), str(SOURCE), "-L" + libs, "-lQt6Core",
                    "-o", str(binary)]
            built = subprocess.run(args, cwd=str(work), env=env,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=180,
                                   check=False)
            self.assertEqual(built.returncode, 0,
                             built.stdout.decode("utf-8", "replace")[-4000:])
            env["QT_FORCE_STDERR_LOGGING"] = "1"
            env.pop("DISPLAY", None)
            run = subprocess.run([str(binary)], env=env, cwd=str(work),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=60,
                                 check=False)
            output = run.stdout.decode("utf-8", "replace")
            self.assertEqual(run.returncode, 0, output[-4000:])
            self.assertIn("ND038_ALL_PASS", output)
            seen = {line.split(" ", 1)[1].strip()
                    for line in output.splitlines()
                    if line.startswith("ND038_PASS ")}
            for marker in MARKERS:
                self.assertIn(marker, seen, marker + "\n" + output[-2000:])


if __name__ == "__main__":
    unittest.main()
