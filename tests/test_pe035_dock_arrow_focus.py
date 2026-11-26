"""PE-035 regression: real dock arrow-key focus movement.

The gate's ``dock_arrow_next`` step (tools/qa/classic_keyboard_accessibility_gate.py
lines 109 and 190) claims that Right moves focus from the "Files preview" tile
to "Browser preview". QA-005 proved that claim rested only on a geometry
marker: no QML/C++ key handler existed.

These tests do not assert a gate marker. They exercise the runtime handler
installed on DockTile.qml:
  * source-level checks that each key handler moves real Qt active focus;
  * a pure-JS execution of the same index function the QML handlers call;
  * an offscreen Qt 6 harness that loads the real DockTile.qml, sends actual
    Right/Left/Home/End key events and checks activeFocus before/after.

The compiled harness is skipped only when the Qt 6 C++/pkg-config toolchain is
absent; everything else runs unconditionally. No full application build, VM or
desktop session is used. Runtime results are synthetic/offscreen, NOT Mint
acceptance and NOT screen-reader evidence.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCK_TILE = ROOT / "prototype" / "classic" / "DockTile.qml"
MAIN_QML = ROOT / "prototype" / "classic" / "Main.qml"

PURE_LOGIC_BEGIN = "// BEGIN PE-035 PURE FOCUS INDEX LOGIC"
PURE_LOGIC_END = "// END PE-035 PURE FOCUS INDEX LOGIC"

JS_HARNESS = r"""
%s
const cases = [
  [[0, 3, 1, undefined], 1, "Right: Files -> Browser"],
  [[1, 3, -1, undefined], 0, "Left: Browser -> Files"],
  [[2, 3, 1, undefined], 0, "Right wraps at end"],
  [[0, 3, -1, undefined], 2, "Left wraps at start"],
  [[-1, 3, 1, undefined], 0, "no focus, Right -> first"],
  [[-1, 3, -1, undefined], 2, "no focus, Left -> last"],
  [[1, 3, 0, 0], 0, "Home -> first"],
  [[1, 3, 0, 2], 2, "End -> last"],
  [[1, 3, 0, 99], 2, "absolute index clamped"],
  [[0, 0, 1, undefined], -1, "empty dock has no target"]
];
for (const [args, expected, label] of cases) {
  const actual = dockFocusIndex(...args);
  if (actual !== expected) {
    console.error("PE035_JS_FAIL " + label + " expected=" + expected + " actual=" + actual);
    process.exit(1);
  }
}
console.log("PE035_JS_ALL_PASS cases=" + cases.length);
"""

WRAPPER_QML = """import QtQuick
import QtQuick.Controls
import pe035dock 1.0
Row {
    objectName: "pe035Row"
    Repeater {
        model: ["Files", "Browser", "Settings"]
        DockTile {
            required property var modelData
            iconName: modelData
        }
    }
}
"""

QMLLDIR = "module pe035dock\nDockTile 1.0 DockTile.qml\n"

CPP_PROBE = r"""
#include <QGuiApplication>
#include <QCoreApplication>
#include <QKeyEvent>
#include <QDebug>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QUrl>
#include <algorithm>

static bool check(bool ok, const char *name) {
    qInfo().noquote() << (ok ? "PE035_RUNTIME_PASS " : "PE035_RUNTIME_FAIL ") << name;
    return ok;
}
static QQuickItem *focusedTile(QQuickWindow &window) {
    QQuickItem *item = window.activeFocusItem();
    return (item && item->objectName() == QLatin1String("canopyDockTile"))
        ? item : nullptr;
}
static QString tileName(QQuickItem *item) {
    return item ? item->property("iconName").toString() + QStringLiteral(" preview")
                : QStringLiteral("<none>");
}
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    if (argc < 3) return 2;
    QQmlEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("canopyApprovedMode"), false);
    engine.addImportPath(QString::fromLocal8Bit(argv[1]));
    QQmlComponent component(&engine, QUrl::fromLocalFile(QString::fromLocal8Bit(argv[2])));
    if (component.isError()) {
        qInfo().noquote() << "PE035_QML_LOAD_FAIL" << component.errorString();
        return 3;
    }
    QObject *created = component.create();
    auto *row = qobject_cast<QQuickItem *>(created);
    if (!row) return 4;
    QQuickWindow window;
    window.resize(400, 100);
    row->setParentItem(window.contentItem());
    window.show();
    QCoreApplication::processEvents();
    QList<QQuickItem *> tiles;
    for (QQuickItem *child : row->childItems()) {
        if (child->objectName() == QLatin1String("canopyDockTile")) tiles.append(child);
    }
    std::sort(tiles.begin(), tiles.end(),
              [](QQuickItem *a, QQuickItem *b) { return a->x() < b->x(); });
    bool ok = check(tiles.size() == 3, "three real dock tiles");
    if (!ok) return 1;
    auto key = [&](Qt::Key code) {
        QKeyEvent press(QEvent::KeyPress, code, Qt::NoModifier);
        QGuiApplication::sendEvent(&window, &press);
        QKeyEvent release(QEvent::KeyRelease, code, Qt::NoModifier);
        QGuiApplication::sendEvent(&window, &release);
        QCoreApplication::processEvents();
    };
    tiles[0]->forceActiveFocus();
    QCoreApplication::processEvents();
    ok &= check(focusedTile(window) == tiles[0]
                && tileName(focusedTile(window)) == QStringLiteral("Files preview"),
                "initial focus Files preview");
    key(Qt::Key_Right);
    ok &= check(focusedTile(window) == tiles[1]
                && tileName(focusedTile(window)) == QStringLiteral("Browser preview"),
                "Right moves focus to Browser preview");
    key(Qt::Key_Left);
    ok &= check(focusedTile(window) == tiles[0], "Left returns to Files preview");
    key(Qt::Key_End);
    ok &= check(focusedTile(window) == tiles[2], "End moves focus to last tile");
    key(Qt::Key_Home);
    ok &= check(focusedTile(window) == tiles[0], "Home moves focus to first tile");
    key(Qt::Key_Left);
    ok &= check(focusedTile(window) == tiles[2], "Left wraps to last tile");
    qInfo().noquote() << (ok ? "PE035_RUNTIME_ALL_PASS" : "PE035_RUNTIME_ALL_FAIL");
    return ok ? 0 : 1;
}
"""


def _uCRT_env():
    env = os.environ.copy()
    env["PATH"] = "C:/msys64/ucrt64/bin" + os.pathsep + env.get("PATH", "")
    return env


def _qt_toolchain():
    env = _uCRT_env()
    gpp = shutil.which("g++", path=env["PATH"])
    pkg = shutil.which("pkg-config", path=env["PATH"])
    if not gpp or not pkg:
        return None
    probe = subprocess.run(
        [pkg, "--exists", "Qt6Quick", "Qt6Qml", "Qt6Gui", "Qt6Core"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, env=env,
        timeout=30)
    if probe.returncode != 0:
        return None
    flags = subprocess.run(
        [pkg, "--cflags", "--libs", "Qt6Quick", "Qt6Qml", "Qt6Gui", "Qt6Core"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, env=env,
        timeout=30)
    if flags.returncode != 0:
        return None
    return gpp, flags.stdout.decode("utf-8", "replace").split()


class DockArrowSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tile = DOCK_TILE.read_text(encoding="utf-8")
        cls.main = MAIN_QML.read_text(encoding="utf-8")

    def test_default_dock_order_makes_right_from_files_go_to_browser(self):
        match = re.search(r"canopyApprovedMode\s*\?\s*\[(.*?)\]\s*:",
                          self.main, re.DOTALL)
        self.assertIsNotNone(match)
        approved = re.findall(r'title:\s*"([^"]+)"', match.group(1))
        default = re.findall(r'title:\s*"([^"]+)"', self.main[match.end():])
        self.assertEqual(approved[:3], ["Browser", "Mail", "Files"])
        self.assertEqual(default[:3], ["Files", "Browser", "Settings"])
        self.assertEqual(default.index("Files") + 1, default.index("Browser"))

    def test_each_navigation_key_has_a_runtime_focus_handler(self):
        for handler in ("Keys.onRightPressed", "Keys.onLeftPressed",
                        "Keys.onPressed"):
            with self.subTest(handler=handler):
                self.assertIn(handler, self.tile)
        for key in ("Qt.Key_Home", "Qt.Key_End"):
            with self.subTest(key=key):
                self.assertIn(key, self.tile)
        self.assertIn("event.accepted = true", self.tile)
        self.assertIn("forceActiveFocus()", self.tile)
        self.assertIn("activeFocusOnTab: true", self.tile)

    def test_handlers_move_focus_not_a_geometry_marker(self):
        for needle in ("dockSiblings()", "dockFocusIndex(", "forceActiveFocus()",
                       "Keys.onRightPressed: function(event)",
                       "Keys.onLeftPressed: function(event)",
                       "Keys.onPressed: function(event)"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.tile)
        for forbidden in ("SELF_TEST_PASS", "border_width"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.tile)

    def test_pure_focus_index_logic_is_executable_from_qml_source(self):
        self.assertIn(PURE_LOGIC_BEGIN, self.tile)
        self.assertIn(PURE_LOGIC_END, self.tile)
        logic = self.tile.split(PURE_LOGIC_BEGIN, 1)[1].split(PURE_LOGIC_END, 1)[0]
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available for JS logic probe")
        with tempfile.TemporaryDirectory(prefix="pe035-js-") as folder:
            script = Path(folder) / "probe.js"
            script.write_text(JS_HARNESS % logic, encoding="utf-8")
            run = subprocess.run([node, str(script)], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, check=False, timeout=30)
        output = run.stdout.decode("utf-8", "replace")
        self.assertEqual(run.returncode, 0, output[-2000:])
        self.assertIn("PE035_JS_ALL_PASS cases=10", output)


@unittest.skipUnless(_qt_toolchain(), "Qt 6 C++/pkg-config toolchain not available")
class DockArrowRuntimeTests(unittest.TestCase):
    """Real offscreen key dispatch against the actual DockTile.qml."""

    def test_arrow_home_end_keys_move_qt_active_focus(self):
        tool = _qt_toolchain()
        self.assertIsNotNone(tool)
        gpp, qt_flags = tool
        env = _uCRT_env()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["QT_QUICK_BACKEND"] = "software"
        env["QT_QUICK_CONTROLS_STYLE"] = "Basic"
        env["QT_FORCE_STDERR_LOGGING"] = "1"
        with tempfile.TemporaryDirectory(prefix="pe035-qt-") as folder:
            work = Path(folder)
            module = work / "pe035dock"
            module.mkdir()
            shutil.copyfile(DOCK_TILE, module / "DockTile.qml")
            (module / "qmldir").write_text(QMLLDIR, encoding="utf-8")
            (work / "wrapper.qml").write_text(WRAPPER_QML, encoding="utf-8")
            source = work / "probe.cpp"
            source.write_text(CPP_PROBE, encoding="utf-8")
            binary = work / "probe.exe"
            compile_cmd = [gpp, "-std=c++17", "-fPIC", str(source), *qt_flags,
                           "-o", str(binary)]
            built = subprocess.run(compile_cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, check=False,
                                   timeout=300, env=env, cwd=str(work))
            self.assertEqual(built.returncode, 0, built.stdout.decode(
                "utf-8", "replace")[-4000:])
            run = subprocess.run([str(binary), str(module), str(work / "wrapper.qml")],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 check=False, timeout=120, env=env, cwd=str(work))
        output = run.stdout.decode("utf-8", "replace")
        self.assertEqual(run.returncode, 0, output[-4000:])
        self.assertIn("PE035_RUNTIME_ALL_PASS", output)
        for marker in ("initial focus Files preview",
                       "Right moves focus to Browser preview",
                       "Left returns to Files preview",
                       "End moves focus to last tile",
                       "Home moves focus to first tile",
                       "Left wraps to last tile"):
            with self.subTest(marker=marker):
                self.assertIn("PE035_RUNTIME_PASS  " + marker, output)
        self.assertNotIn("PE035_RUNTIME_FAIL", output)


if __name__ == "__main__":
    unittest.main()
