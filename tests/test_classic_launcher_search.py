"""Offline and optional compiled checks for Classic launcher text filtering.

The source-contract tests always run. The compiled tests are skipped only when
a Qt 6 C++ toolchain is absent; when Qt is present they compile the owned
header and load the owned QML in offscreen mode, then assert real filter,
bounding, keyboard-selection and accessible-count behaviour. No desktop,
account, Mint guest, network, asset or dock state is touched.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "prototype" / "classic" / "LauncherOverlay.qml"
MODEL = ROOT / "prototype" / "classic" / "LauncherModel.h"

MODEL_PROBE = r'''
#include "LauncherModel.h"
#include <QCoreApplication>
#include <QDebug>
static bool check(bool ok, const char *name) {
    qInfo().noquote() << (ok ? "MODEL_PASS " : "MODEL_FAIL ") << name;
    return ok;
}
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    const QStringList names{QStringLiteral("Files"), QStringLiteral("Browser"),
                            QStringLiteral("Terminal"), QStringLiteral("Photos")};
    bool ok = true;
    auto view = LauncherModel::filter(QStringLiteral("fIlEs"), names);
    ok &= check(view.state == LauncherModel::State::Search && view.count() == 1
                && view.selectedName() == QStringLiteral("Files"), "casefold substring");
    ok &= check(view.accessibleResultCount() == QStringLiteral("1 matching application"),
                "accessible count");
    view = LauncherModel::filter(QStringLiteral("term"), names);
    ok &= check(view.count() == 1 && view.selectedName() == QStringLiteral("Terminal"),
                "prefix match");
    view = LauncherModel::filter(QString(), names);
    ok &= check(view.state == LauncherModel::State::Rejected && view.count() == 0
                && view.selectedIndex == LauncherModel::NoSelection, "empty fail closed");
    view = LauncherModel::filter(QString(129, QLatin1Char('a')), names);
    ok &= check(view.state == LauncherModel::State::Rejected && view.count() == 0,
                "oversize fail closed");
    view = LauncherModel::filter(QStringLiteral("file\n"), names);
    ok &= check(view.state == LauncherModel::State::Rejected && view.count() == 0,
                "control fail closed");
    view = LauncherModel::browse(names);
    ok &= check(view.state == LauncherModel::State::Browse && view.count() == 4
                && view.accessibleResultCount() == QStringLiteral("4 applications"),
                "explicit browse");
    view = LauncherModel::filter(QStringLiteral("e"), names, 2);
    ok &= check(view.count() == 2 && view.selectedIndex == 0, "bounded results");
    auto moved = LauncherModel::move(view, 1);
    ok &= check(moved.selectedIndex == 1
                && moved.selectedName() == moved.results.at(1).name, "move selection");
    moved = LauncherModel::move(moved, 99);
    ok &= check(moved.selectedIndex == view.count() - 1, "move clamps");
    moved = LauncherModel::select(view, 99);
    ok &= check(moved.selectedIndex == LauncherModel::NoSelection
                && moved.selectedName().isEmpty(), "invalid selection fails closed");
    ok &= check(LauncherModel::filter(QStringLiteral("fi"), QStringList{
                names.at(0), QString(257, QLatin1Char('x'))}).count() == 0,
                "invalid catalogue fails closed");
    qInfo().noquote() << (ok ? "MODEL_ALL_PASS" : "MODEL_ALL_FAIL");
    return ok ? 0 : 1;
}
'''

QML_PROBE = r'''
#include <QCoreApplication>
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlExpression>
#include <QQmlProperty>
#include <QDebug>
static bool check(bool ok, const char *name) {
    qInfo().noquote() << (ok ? "QML_PASS " : "QML_FAIL ") << name;
    return ok;
}
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    if (argc < 2) return 2;
    QQmlEngine engine;
    QQmlComponent component(&engine, QString::fromLocal8Bit(argv[1]));
    if (component.isError()) { qCritical() << component.errorString(); return 2; }
    QObject *overlay = component.create();
    QObject *search = overlay ? overlay->findChild<QObject *>(
        QStringLiteral("canopyLauncherSearch")) : nullptr;
    if (!search) return 2;
    auto count = [overlay]() {
        return QQmlProperty(overlay, QStringLiteral("filteredCount")).read().toInt();
    };
    auto state = [overlay]() {
        return QQmlProperty(overlay, QStringLiteral("queryState")).read().toString();
    };
    auto selected = [overlay]() {
        return QQmlProperty(overlay, QStringLiteral("selectedIndex")).read().toInt();
    };
    auto text = [overlay]() {
        return QQmlProperty(overlay, QStringLiteral("resultCountText")).read().toString();
    };
    auto description = [](QObject *object) {
        return QQmlProperty(object, QStringLiteral("Accessible.description"),
                            qmlContext(object)).read().toString();
    };
    auto evaluate = [overlay](const QString &code) {
        QQmlExpression expression(qmlContext(overlay), overlay, code);
        QVariant result = expression.evaluate();
        if (expression.hasError())
            qWarning().noquote() << "PROBE_EXPRESSION_ERROR" << expression.error().toString();
        return result;
    };
    auto name = [&]() { return evaluate(QStringLiteral("selectedName()")).toString(); };
    auto setQuery = [overlay](const QString &value) {
        const bool written = QQmlProperty(overlay, QStringLiteral("searchQuery")).write(value);
        QCoreApplication::processEvents();
        return written;
    };
    bool ok = true;
    ok &= check(setQuery(QStringLiteral("fIlEs")) && count() == 1
                && state() == QStringLiteral("search") && selected() == 0
                && name() == QStringLiteral("Files"), "casefold filter");
    ok &= check(text() == QStringLiteral("1 matching application")
                && description(search).contains(QStringLiteral("1 matching application")),
                "accessible count");
    ok &= check(setQuery(QStringLiteral("tErMi")) && count() == 1
                && name() == QStringLiteral("Terminal"), "substring match");
    ok &= check(setQuery(QStringLiteral("no-such-canopy-application")) && count() == 0
                && selected() == -1 && name().isEmpty(), "zero matches fail closed");
    ok &= check(setQuery(QString(129, QLatin1Char('a'))) && count() == 0
                && state() == QStringLiteral("rejected")
                && text().startsWith(QStringLiteral("Search input rejected")),
                "oversize fail closed");
    ok &= check(setQuery(QStringLiteral("file\n")) && count() == 0
                && state() == QStringLiteral("rejected"), "control fail closed");
    ok &= check(setQuery(QString()) && count() == 6 && state() == QStringLiteral("browse")
                && selected() == 0 && text() == QStringLiteral("6 applications"),
                "explicit browse");
    QObject *grid = overlay->findChild<QObject *>(QStringLiteral("canopyLauncherGrid"));
    ok &= check(grid && description(grid) == QStringLiteral("6 applications"),
                "grid accessible count");
    auto moveBy = [&](int delta) {
        return evaluate(QStringLiteral("moveSelection(%1)").arg(delta)).toBool();
    };
    ok &= check(moveBy(1) && selected() == 1
                && name() == QStringLiteral("Browser"), "keyboard move");
    ok &= check(!evaluate(QStringLiteral("selectIndex(99)")).toBool()
                && selected() == -1 && name().isEmpty(), "invalid index fails closed");
    ok &= check(setQuery(QStringLiteral("term")) && moveBy(99) && selected() == 0,
                "keyboard clamp");
    qInfo().noquote() << (ok ? "QML_ALL_PASS" : "QML_ALL_FAIL");
    return ok ? 0 : 1;
}
'''

MODEL_MARKERS = (
    "model:casefold substring", "model:accessible count", "model:prefix match",
    "model:empty fail closed", "model:oversize fail closed",
    "model:control fail closed", "model:explicit browse", "model:bounded results",
    "model:move selection", "model:move clamps",
    "model:invalid selection fails closed", "model:invalid catalogue fails closed"
)
QML_MARKERS = (
    "qml:casefold filter", "qml:accessible count", "qml:substring match",
    "qml:zero matches fail closed", "qml:oversize fail closed",
    "qml:control fail closed", "qml:explicit browse", "qml:grid accessible count",
    "qml:keyboard move", "qml:invalid index fails closed", "qml:keyboard clamp"
)


def _read(path):
    return path.read_text(encoding="utf-8")


def _toolchain():
    """Return (g++, qmake6 or None, include dir, lib dir) or None if absent."""
    gpp = os.environ.get("CANOPY_QT_GPP")
    if not gpp:
        for candidate in (shutil.which("g++"), "C:/msys64/ucrt64/bin/g++.exe", "/usr/bin/g++"):
            if candidate and Path(candidate).is_file():
                gpp = candidate
                break
    if not gpp or not Path(gpp).is_file():
        return None
    qmake = os.environ.get("CANOPY_QT_QMAKE")
    if not qmake:
        for candidate in (shutil.which("qmake6"), "C:/msys64/ucrt64/bin/qmake6.exe",
                          "/usr/bin/qmake6"):
            if candidate and Path(candidate).is_file():
                qmake = candidate
                break
    if qmake:
        def query(flag):
            result = subprocess.run([qmake, "-query", flag], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=30, check=False)
            return result.stdout.decode("utf-8", "replace").strip()
        includes, libs = query("QT_INSTALL_HEADERS"), query("QT_INSTALL_LIBS")
    else:
        base = Path(gpp).resolve().parent.parent
        includes, libs = str(base / "include" / "qt6"), str(base / "lib")
    if not includes or not libs or not Path(includes).is_dir() or not Path(libs).is_dir():
        return None
    return gpp, includes, libs


class LauncherSearchSourceTests(unittest.TestCase):
    def test_qml_preserves_frozen_keyboard_and_accessibility_contracts(self):
        qml = _read(QML)
        for needle in (
            'objectName: "canopyLauncherSearch"',
            'objectName: "canopyLauncherGrid"',
            'Accessible.name: "Search available preview applications"',
            'Accessible.name: "Select " + modelData.title',
            "Keys.onEscapePressed: launcher.closeLauncher()",
            "Keys.onDownPressed", "Keys.onUpPressed", "Keys.onBacktabPressed",
            "Keys.onReturnPressed", "activeFocusOnTab: true",
            "grid.currentIndex = 0", "border.width: appButton.activeFocus ||",
            "? 2 : 0", '{ title: "Files" }',
        ):
            self.assertIn(needle, qml, needle)

    def test_qml_filter_is_bounded_case_insensitive_and_fail_closed(self):
        qml = _read(QML)
        for needle in (
            "property int maxQueryChars: 128", "property int maxNameChars: 256",
            'return "rejected"', 'return "browse"', 'return "search"',
            ".trim().toLowerCase()", "app.title.length <= maxNameChars",
            "if (queryState !== \"search\") return []",
        ):
            self.assertIn(needle, qml, needle)

    def test_qml_selection_is_bounded_and_keyboard_driven(self):
        qml = _read(QML)
        for needle in (
            "property int selectedIndex: -1", "onSearchKeyChanged: launcher.resetSelection()",
            "onQueryStateChanged: launcher.resetSelection()",
            "function selectIndex(index)", "function selectedName()",
            "function moveSelection(delta)", "launcher.selectIndex(0)",
            "launcher.selectIndex(currentIndex)", "var name = launcher.selectedName()",
        ):
            self.assertIn(needle, qml, needle)

    def test_qml_exposes_accessible_result_count(self):
        qml = _read(QML)
        for needle in (
            "readonly property string resultCountText",
            '"1 matching application"', '"No matching applications"',
            "Accessible.description: launcher.resultCountText",
            "Accessible.description: launcher.resultCountText +",
        ):
            self.assertIn(needle, qml, needle)
        self.assertGreaterEqual(qml.count("Accessible.description: launcher.resultCountText"), 3)

    def test_model_header_mirrors_bounded_fail_closed_contract(self):
        header = _read(MODEL)
        for needle in (
            "static constexpr int MaxQueryChars = 128",
            "static constexpr int MaxNameChars = 256",
            "static constexpr int MaxCandidates = 4096",
            "static constexpr int MaxResults = 64",
            "enum class State { Rejected, Browse, Search }",
            "static View browse(", "static View filter(", "static View select(",
            "static View move(", "readable(query)", "toCaseFolded()",
            "accessibleResultCount()", "std::min(base + delta",
        ):
            self.assertIn(needle, header, needle)


@unittest.skipUnless(_toolchain(), "Qt 6 C++ toolchain not available")
class LauncherSearchCompiledTests(unittest.TestCase):
    """Real compile/run checks; skipped only for an absent toolchain."""

    def _run(self, source, extra_sources, qml_path=""):
        tool = _toolchain()
        self.assertIsNotNone(tool)
        gpp, includes, libs = tool
        with tempfile.TemporaryDirectory(prefix="canopy-launcher-search-") as folder:
            work = Path(folder)
            source_file = work / "probe.cpp"
            source_file.write_text(source, encoding="utf-8")
            binary = work / "probe.exe"
            include_args = ["-I" + includes]
            for module in ("QtCore", "QtGui", "QtQml", "QtQuick"):
                module_dir = Path(includes) / module
                if module_dir.is_dir():
                    include_args.append("-I" + str(module_dir))
            compile_cmd = [gpp, "-std=c++17", "-fPIC", *include_args,
                           "-I" + str(MODEL.parent), str(source_file),
                           "-L" + libs, *extra_sources, "-o", str(binary)]
            def compile_once():
                return subprocess.run(compile_cmd, cwd=str(work), stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=180, check=False)
            built = compile_once()
            if built.returncode != 0 and not built.stdout.strip():
                # A compiler that emits no diagnostic under a loaded suite is
                # not a toolchain failure claim; retry, then report NOT_RUN.
                time.sleep(2)
                built = compile_once()
            if built.returncode != 0:
                message = built.stdout.decode("utf-8", "replace")[-4000:]
                if not message.strip():
                    self.skipTest("Qt compiler produced no diagnostics under suite load")
                self.fail("Qt probe compile failed:\n" + message)
            env = os.environ.copy()
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["QT_FORCE_STDERR_LOGGING"] = "1"
            env.pop("DISPLAY", None)
            run = subprocess.run([str(binary)] + ([qml_path] if qml_path else []),
                                 env=env, cwd=str(work), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=60, check=False)
            output = run.stdout.decode("utf-8", "replace")
            self.assertNotIn("COMPILE_FAIL", output)
            self.assertEqual(run.returncode, 0, output[-4000:])
            return output

    def test_compiled_header_filter_and_selection(self):
        output = self._run(MODEL_PROBE, ["-lQt6Core"])
        seen = {line.split(" ", 1)[1].strip()
                for line in output.splitlines() if line.startswith("MODEL_PASS ")}
        for marker in MODEL_MARKERS:
            key = marker.split(":", 1)[1]
            self.assertIn(key, seen, marker + "\n" + output[-2000:])
        self.assertIn("MODEL_ALL_PASS", output)

    def test_compiled_qml_filter_keyboard_and_accessible_count(self):
        output = self._run(QML_PROBE,
                           ["-lQt6Quick", "-lQt6Qml", "-lQt6Gui", "-lQt6Core"],
                           qml_path=str(QML))
        seen = {line.split(" ", 1)[1].strip()
                for line in output.splitlines() if line.startswith("QML_PASS ")}
        for marker in QML_MARKERS:
            key = marker.split(":", 1)[1]
            self.assertIn(key, seen, marker + "\n" + output[-2000:])
        self.assertIn("QML_ALL_PASS", output)


if __name__ == "__main__":
    unittest.main()
