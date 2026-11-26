"""PE-003 regression lock for the opt-in Classic launcher catalogue bridge.

The production wiring (LauncherCatalogBridge, the --launcher-catalog flag,
canopyLauncherCatalog QML context property and the count/title self-test) is
already present at the integration tip. These checks lock that compiled host
contract in the repository, so a later refactor cannot silently disconnect the
validated model from the running launcher or weaken its fail-closed defaults.

Source-contract only: no build, no desktop, no Mint session and no visual
acceptance is claimed here.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "prototype" / "classic"
MAIN = PROTO / "main.cpp"
QML = PROTO / "LauncherOverlay.qml"
CMAKE = PROTO / "CMakeLists.txt"


def main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


def before(text: str, marker: str) -> str:
    """Source text before the first occurrence of marker (empty if absent)."""
    at = text.find(marker)
    return text if at < 0 else text[:at]


class RuntimeBridgeWiringTests(unittest.TestCase):
    def test_bridge_is_a_read_only_compiled_host_face(self):
        source = main_source()
        self.assertIn("class LauncherCatalogBridge final : public QObject", source)
        for needle in (
            "Q_PROPERTY(bool active READ active CONSTANT)",
            "Q_PROPERTY(int rowCount READ rowCount CONSTANT)",
            "Q_INVOKABLE QVariantList applications() const",
            "const LauncherCatalogModel &m_model",
        ):
            self.assertIn(needle, source, needle)
        bridge = source[source.index("class LauncherCatalogBridge"):]
        bridge = bridge[:bridge.index("\n};")]
        for forbidden in ("QProcess", "QTcpSocket", "QNetwork", "QTimer",
                          "QDirIterator", "QFile", "system(", "popen("):
            self.assertNotIn(forbidden, bridge, forbidden)

    def test_model_and_bridge_outlive_the_qml_engine(self):
        source = main_source()
        model_at = source.index("LauncherCatalogModel launcherCatalog;")
        bridge_at = source.index("LauncherCatalogBridge launcherCatalogBridge(launcherCatalog);")
        engine_at = source.index("QQmlApplicationEngine engine;")
        self.assertLess(model_at, bridge_at)
        self.assertLess(bridge_at, engine_at)
        self.assertIn(
            'QStringLiteral("canopyLauncherCatalog"), &launcherCatalogBridge);',
            source,
        )
        registered_at = source.index('QStringLiteral("canopyLauncherCatalog")')
        loaded_at = source.index('engine.load(QUrl(QStringLiteral("qrc:/Canopy/Classic/Main.qml")))')
        self.assertLess(registered_at, loaded_at)
        self.assertIn('typeof canopyLauncherCatalog', QML.read_text(encoding="utf-8"))

    def test_opt_in_catalog_flag_is_explicit_and_fails_closed(self):
        source = main_source()
        self.assertIn('QStringLiteral("--launcher-catalog")', source)
        block = source[source.index('const int launcherCatalogIndex = args.indexOf('):]
        block = block[:block.index("const bool launcherFixture")]
        self.assertIn("args.at(launcherCatalogIndex + 1).startsWith(QLatin1Char('-'))", block)
        self.assertIn("CANOPY_LAUNCHER_CATALOG_REJECTED_FAIL_CLOSED: missing path", block)
        self.assertIn("launcherCatalog.loadFromFile(", block)
        self.assertIn("CANOPY_LAUNCHER_CATALOG_CONNECTED: opt-in rows", block)
        self.assertIn("CANOPY_LAUNCHER_CATALOG_REJECTED_FAIL_CLOSED\"", block)
        # No implicit discovery path: only one explicit read-only file load.
        self.assertEqual(source.count("launcherCatalog.loadFromFile("), 1)

    def test_model_self_test_flag_exits_before_the_desktop_is_built(self):
        source = main_source()
        self.assertIn('QStringLiteral("--self-test-launcher-catalog-model")', source)
        self.assertIn("return LauncherCatalogModel::selfTest() ? 0 : 1;", source)
        self.assertLess(
            source.index("return LauncherCatalogModel::selfTest() ? 0 : 1;"),
            source.index("QQmlApplicationEngine engine;"),
        )
        self.assertLess(
            source.index("return LauncherCatalogModel::selfTest() ? 0 : 1;"),
            source.index("CANOPY_LAUNCHER_CATALOG_CONNECTED"),
        )

    def test_runtime_self_test_proves_count_and_title_order(self):
        source = main_source()
        for needle in (
            "const bool launcherCatalogActive = launcherCatalog.active();",
            "? launcherCatalog.rowCount() : (approvedMode ? 8 : 6);",
            "? launcherCatalog.titles() : QStringList();",
            'applicationLauncher->property("applications").toList()',
            'actual.size() == expectedLauncherTitles.size()',
            '.value(QStringLiteral("title")).toString()',
            "== expectedLauncherTitles.at(i);",
            "if (!selectedMatch || !emptyMatch || !restoredMatch || !catalogMatches",
            '"SELF_TEST_PASS: opt-in desktop-entry catalogue reached QML"',
            "<< expectedLauncherCount;",
        ):
            self.assertIn(needle, source, needle)
        self.assertLess(
            source.index("? launcherCatalog.titles() : QStringList();"),
            source.index('applicationLauncher->property("applications").toList()'),
        )

    def test_approved_default_catalogue_and_cmake_sources_stay_intact(self):
        qml = QML.read_text(encoding="utf-8")
        for needle in ('{ title: "Browser" }, { title: "Mail" },',
                       '{ title: "Files" }, { title: "Browser" },',
                       "canopyLauncherCatalog.active",
                       "canopyLauncherCatalog.applications()"):
            self.assertIn(needle, qml, needle)
        cmake = CMAKE.read_text(encoding="utf-8")
        self.assertRegex(
            cmake,
            re.escape("qt_add_executable(canopy-classic-spike main.cpp ")
            + r"LauncherModel\.cpp LauncherModel\.h ",
        )


if __name__ == "__main__":
    unittest.main()
