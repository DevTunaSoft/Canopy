import QtQuick
import QtQuick.Controls

// Original, macOS-familiar menus for the Classic prototype. Every item acts
// on the in-preview Files window through its explicit interface. No session
// services, global shortcuts, shell commands or copied artwork are involved.
Item {
    id: shellMenus
    objectName: "canopyShellMenuBar"

    // filesPreview is supplied by Main.qml. The interface used below is:
    // currentPath, searchQuery, canGoBack, canGoUp; navigate(string), goBack(),
    // goUp(), setSearch(string), requestClose(); closed().
    property var filesWindow: null
    property string homePath: "Home"

    signal showLauncherRequested()
    signal aboutRequested()

    // Bounded nonvisual startup change: the six approved popups live in their
    // own QML document and are neither compiled into the resting scene nor
    // instantiated until a menu is actually opened. Stable proxies keep the
    // menuFor()/open()/visible contract unchanged for Main.qml and self-tests.
    Loader {
        id: menusLoader
        active: false
        source: "ShellMenuPopupSet.qml"
        onLoaded: {
            menusLoader.item.filesWindow = Qt.binding(function() { return shellMenus.filesWindow })
            menusLoader.item.homePath = Qt.binding(function() { return shellMenus.homePath })
        }
    }

    Connections {
        target: menusLoader.item
        function onShowLauncherRequested() { shellMenus.showLauncherRequested() }
        function onAboutRequested() { shellMenus.aboutRequested() }
    }

    QtObject {
        id: fileMenu
        property bool visible: menusLoader.item ? menusLoader.item.menuFor("File").visible : false
        function open() {
            if (!menusLoader.active)
                menusLoader.active = true
            menusLoader.item.menuFor("File").open()
        }
    }
    QtObject {
        id: editMenu
        property bool visible: menusLoader.item ? menusLoader.item.menuFor("Edit").visible : false
        function open() {
            if (!menusLoader.active)
                menusLoader.active = true
            menusLoader.item.menuFor("Edit").open()
        }
    }
    QtObject {
        id: viewMenu
        property bool visible: menusLoader.item ? menusLoader.item.menuFor("View").visible : false
        function open() {
            if (!menusLoader.active)
                menusLoader.active = true
            menusLoader.item.menuFor("View").open()
        }
    }
    QtObject {
        id: goMenu
        property bool visible: menusLoader.item ? menusLoader.item.menuFor("Go").visible : false
        function open() {
            if (!menusLoader.active)
                menusLoader.active = true
            menusLoader.item.menuFor("Go").open()
        }
    }
    QtObject {
        id: windowMenu
        property bool visible: menusLoader.item ? menusLoader.item.menuFor("Window").visible : false
        function open() {
            if (!menusLoader.active)
                menusLoader.active = true
            menusLoader.item.menuFor("Window").open()
        }
    }
    QtObject {
        id: helpMenu
        property bool visible: menusLoader.item ? menusLoader.item.menuFor("Help").visible : false
        function open() {
            if (!menusLoader.active)
                menusLoader.active = true
            menusLoader.item.menuFor("Help").open()
        }
    }

    function menuFor(name) {
        switch (name) {
        case "File": return fileMenu
        case "Edit": return editMenu
        case "View": return viewMenu
        case "Go": return goMenu
        case "Window": return windowMenu
        case "Help": return helpMenu
        default: return null
        }
    }
}
