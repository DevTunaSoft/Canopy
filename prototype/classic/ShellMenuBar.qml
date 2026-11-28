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

    // The bar owns the palette instance and hands it to the deferred popup
    // payload. All presentation values come from the existing Theme tokens:
    // no new color, artwork, geometry, timer, daemon or menu action.
    Theme { id: menuTheme }

    readonly property var menuPalette: menuTheme
    readonly property var menuPresentation: menusLoader.item
                                            ? menusLoader.item.presentation
                                            : null

    // Bounded nonvisual startup change: the six approved popups live in their
    // own QML document and are neither compiled into the resting scene nor
    // instantiated until a menu is actually opened. Stable proxies keep the
    // menuFor()/open()/visible contract unchanged for Main.qml and self-tests.
    Loader {
        id: menusLoader
        active: false
        source: "ShellMenuPopupSet.qml"
        onLoaded: {
            menusLoader.item.menuPaletteSource = Qt.binding(function() { return menuTheme })
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

    // Compact-width reachability (e.g. 760x500): Main.qml keeps the six
    // approved top-bar buttons but hides Window and Help when compactLayout
    // is active. These non-visual shortcuts reach the same two existing menu
    // proxies by keyboard, without editing Main.qml or changing approved
    // geometry, artwork or menu actions. Alt+W / Alt+H are not registered by
    // the Classic shell (its bindings are Ctrl+Space, Ctrl+W, Ctrl+Shift+F
    // and Ctrl+Alt+N).
    Shortcut {
        objectName: "canopyWindowMenuReachabilityShortcut"
        sequence: "Alt+W"
        context: Qt.ApplicationShortcut
        onActivated: windowMenu.open()
    }
    Shortcut {
        objectName: "canopyHelpMenuReachabilityShortcut"
        sequence: "Alt+H"
        context: Qt.ApplicationShortcut
        onActivated: helpMenu.open()
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
