"""Source-contract tests for the bounded Classic Files browser.

No Qt runtime is needed. These tests keep the C++/QML contract honest:
home-scoped model, capped listing, required shell/menu interface, retained
runtime self-test object names, and no shell, timers or polling.
"""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"


class ClassicFilesBrowserSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = (SOURCE / "FileModel.h").read_text(encoding="utf-8")
        cls.model = (SOURCE / "FileModel.cpp").read_text(encoding="utf-8")
        cls.window = (SOURCE / "PreviewWindow.qml").read_text(encoding="utf-8")
        cls.cmake = (SOURCE / "CMakeLists.txt").read_text(encoding="utf-8")
        cls.main = (SOURCE / "main.cpp").read_text(encoding="utf-8")
        cls.qml_all = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(SOURCE.glob("*.qml"))
        )

    def test_model_is_a_qml_element_in_the_embedded_module(self):
        self.assertIn("class FileModel : public QAbstractListModel", self.header)
        self.assertIn("QML_ELEMENT", self.header)
        self.assertIn("Q_PROPERTY(QString currentPath", self.header)
        self.assertIn("Q_PROPERTY(QString searchQuery", self.header)
        self.assertIn("Q_PROPERTY(bool canGoBack", self.header)
        self.assertIn("Q_PROPERTY(bool canGoUp", self.header)
        self.assertIn("Q_INVOKABLE bool navigate(", self.header)
        self.assertIn("Q_INVOKABLE bool goBack(", self.header)
        self.assertIn("Q_INVOKABLE bool goUp(", self.header)
        self.assertIn("Q_INVOKABLE void setSearch(", self.header)
        self.assertIn("SOURCES FileModel.cpp FileModel.h", self.cmake)
        self.assertIn("import Canopy.Classic", self.window)
        self.assertIn("FileModel { id: fileModel }", self.window)

    def test_listing_is_lazy_and_bounded(self):
        self.assertIn("kMaxEntries = 500", self.header)
        self.assertIn("m_all.size() < kMaxEntries", self.model)
        self.assertIn("QDirIterator it(", self.model)
        self.assertIn("QDirIterator::NoIteratorFlags", self.model)
        self.assertNotIn("QDir::entryInfoList", self.model)
        self.assertIn("beginResetModel();", self.model)
        self.assertIn("endResetModel();", self.model)
        self.assertIn("FileModel::rowCount(", self.model)
        self.assertIn("return parent.isValid() ? 0 : m_visible.size();", self.model)
        self.assertIn("int entryCount() const { return m_visible.size(); }", self.header)
        self.assertIn("int maxEntries() const { return kMaxEntries; }", self.header)
        # Listing only runs from an explicit state change, never a tick.
        for tick in ("QTimer", "setInterval", "Timer {", "Qt.callLater"):
            self.assertNotIn(tick, self.model)
            self.assertNotIn(tick, self.window)

    def test_path_containment_refuses_outside_home(self):
        self.assertIn("QDir::homePath()", self.model)
        self.assertIn("canonicalFilePath()", self.model)
        self.assertIn("resolveUnderHome(", self.model)
        self.assertIn("startsWith(prefix, kCase)", self.model)
        self.assertIn("return QString();", self.model)
        self.assertIn('navigationRejected(QStringLiteral("path outside home or unreadable"))',
                      self.model)
        self.assertIn('navigationRejected(QStringLiteral("path outside home"))', self.model)
        self.assertIn("QFileInfo(target).isDir()", self.model)
        self.assertIn("parent.cdUp()", self.model)
        # No process execution or network access anywhere in the browser.
        for forbidden in ("QProcess", "QNetworkAccessManager", "QUdpSocket",
                          "popen(", "std::system", "::system("):
            self.assertNotIn(forbidden, self.header)
            self.assertNotIn(forbidden, self.model)
            self.assertNotIn(forbidden, self.window)

    def test_shell_and_menu_interface_is_complete(self):
        for prop in ("currentPath", "searchQuery", "canGoBack", "canGoUp"):
            self.assertRegex(
                self.window,
                r"property (?:readonly )?(?:string|bool) " + prop + r"\b",
            )
        for function in ("navigate", "goBack", "goUp", "setSearch", "requestClose"):
            self.assertRegex(self.window, r"function " + function + r"\(")
        self.assertIn("signal closed()", self.window)
        self.assertIn("onVisibleChanged: if (!visible) preview.closed()", self.window)
        self.assertIn("preview.goBack()", self.window)
        self.assertIn("preview.goUp()", self.window)
        self.assertIn("preview.navigate(", self.window)
        self.assertIn("preview.setSearch(text)", self.window)
        self.assertIn("onTextChanged: preview.setSearch(text)", self.window)
        self.assertIn("Keys.onPressed", self.window)
        self.assertIn("Accessible.name: name + (isDir ? \" folder\" : \" file\")",
                      self.window)

    def test_runtime_self_test_object_names_and_properties_survive(self):
        names = set(re.findall(r'QStringLiteral\("(canopy[A-Za-z]+)"\)', self.main))
        # Context properties are C++-provided globals, not QML objectNames.
        names -= set(re.findall(
            r'setContextProperty\(\s*QStringLiteral\("([A-Za-z]+)"\)', self.main))
        self.assertGreater(len(names), 10)
        for name in sorted(names):
            with self.subTest(objectName=name):
                self.assertIn('"' + name + '"', self.qml_all)
        properties = set(re.findall(r'property\("([A-Za-z]+)"\)', self.main))
        properties.add("previewActive")  # used through a live QML binding
        for prop in sorted(properties):
            with self.subTest(property=prop):
                self.assertRegex(self.qml_all, r"\b" + re.escape(prop) + r"\b")

    def test_home_grid_and_approved_visual_contract_unchanged(self):
        self.assertIn('objectName: "canopyPreviewWindow"', self.window)
        self.assertIn('objectName: "canopyPreviewClose"', self.window)
        self.assertIn('Accessible.name: "Close Files preview"', self.window)
        self.assertIn("onClicked: preview.visible = false", self.window)
        self.assertIn('objectName: "canopyPreviewSearch"', self.window)
        self.assertIn('objectName: "canopyFolderScroller"', self.window)
        self.assertIn('objectName: "canopyFolderFlow"', self.window)
        self.assertIn('objectName: "canopySidebarScroller"', self.window)
        self.assertIn('objectName: "canopyFolderTile"',
                      (SOURCE / "FolderTile.qml").read_text(encoding="utf-8"))
        self.assertIn("compact: preview.condensed", self.window)
        self.assertIn("onClicked: preview.selectedFolder = folderName", self.window)
        self.assertIn('name: "Templates"', self.window)
        self.assertIn('name: "Public"', self.window)
        self.assertIn('contentHeight: Math.max(height, folders.height + 10)', self.window)
        self.assertIn("height: childrenRect.height", self.window)
        self.assertIn("width: Math.min(folderScroller.width - 13", self.window)
        self.assertIn("4 * 108 + 3 * (preview.condensed ? 6 : 10)", self.window)
        self.assertIn("assets/ui/folder-blue.svg", self.cmake)
        self.assertNotIn("NumberAnimation", self.window)
        self.assertEqual(len(re.findall(r'\{ name: "[A-Za-z]+", tone:', self.window)), 8)


if __name__ == "__main__":
    unittest.main()
