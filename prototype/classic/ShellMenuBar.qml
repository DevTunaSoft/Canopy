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

    Menu {
        id: fileMenu
        objectName: "canopyMenuFile"
        title: "File"
        MenuItem {
            objectName: "canopyMenuFileOpen"
            text: "Open Files"
            Accessible.name: "Open Files window"
            onTriggered: {
                if (!shellMenus.filesWindow)
                    return
                shellMenus.filesWindow.visible = true
                shellMenus.filesWindow.navigate(shellMenus.homePath)
            }
        }
        MenuItem {
            objectName: "canopyMenuFileClose"
            text: "Close Files"
            Accessible.name: "Close Files window"
            enabled: shellMenus.filesWindow && shellMenus.filesWindow.visible
            onTriggered: shellMenus.filesWindow.requestClose()
        }
        MenuSeparator {}
        MenuItem {
            objectName: "canopyMenuFileHome"
            text: "Go Home"
            Accessible.name: "Go to Files home"
            onTriggered: shellMenus.filesWindow.navigate(shellMenus.homePath)
        }
    }

    Menu {
        id: editMenu
        objectName: "canopyMenuEdit"
        title: "Edit"
        MenuItem {
            objectName: "canopyMenuEditFind"
            text: "Find"
            Accessible.name: "Find in Files"
            onTriggered: shellMenus.filesWindow.setSearch("")
        }
        MenuItem {
            objectName: "canopyMenuEditClear"
            text: "Clear Search"
            Accessible.name: "Clear Files search"
            onTriggered: shellMenus.filesWindow.setSearch("")
        }
    }

    Menu {
        id: viewMenu
        objectName: "canopyMenuView"
        title: "View"
        MenuItem {
            objectName: "canopyMenuViewToggle"
            text: shellMenus.filesWindow && shellMenus.filesWindow.visible
                  ? "Hide Files" : "Show Files"
            Accessible.name: "Toggle Files window"
            onTriggered: {
                if (shellMenus.filesWindow.visible)
                    shellMenus.filesWindow.requestClose()
                else
                    shellMenus.filesWindow.visible = true
            }
        }
        MenuItem {
            objectName: "canopyMenuViewFocusSearch"
            text: "Focus Search"
            Accessible.name: "Focus Files search field"
            onTriggered: shellMenus.filesWindow.setSearch(
                             shellMenus.filesWindow.searchQuery)
        }
        MenuSeparator {}
        MenuItem {
            objectName: "canopyMenuViewPath"
            enabled: false
            text: shellMenus.filesWindow
                  ? "Location: " + shellMenus.filesWindow.currentPath
                  : "Location: unavailable"
            Accessible.name: "Current Files location"
        }
    }

    Menu {
        id: goMenu
        objectName: "canopyMenuGo"
        title: "Go"
        MenuItem {
            objectName: "canopyMenuGoBack"
            text: "Back"
            Accessible.name: "Go back in Files"
            enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoBack
            onTriggered: shellMenus.filesWindow.goBack()
        }
        MenuItem {
            objectName: "canopyMenuGoUp"
            text: "Up"
            Accessible.name: "Go up in Files"
            enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoUp
            onTriggered: shellMenus.filesWindow.goUp()
        }
        MenuSeparator {}
        MenuItem {
            objectName: "canopyMenuGoHome"
            text: "Home"
            Accessible.name: "Go to Files home folder"
            onTriggered: shellMenus.filesWindow.navigate(shellMenus.homePath)
        }
    }

    Menu {
        id: windowMenu
        objectName: "canopyMenuWindow"
        title: "Window"
        MenuItem {
            objectName: "canopyMenuWindowFiles"
            text: "Files"
            Accessible.name: "Bring Files window to front"
            checkable: true
            checked: shellMenus.filesWindow && shellMenus.filesWindow.visible
            onTriggered: shellMenus.filesWindow.visible = checked
        }
        MenuSeparator {}
        MenuItem {
            objectName: "canopyMenuWindowClose"
            text: "Close Files"
            Accessible.name: "Close Files window from Window menu"
            enabled: shellMenus.filesWindow && shellMenus.filesWindow.visible
            onTriggered: shellMenus.filesWindow.requestClose()
        }
    }

    Menu {
        id: helpMenu
        objectName: "canopyMenuHelp"
        title: "Help"
        MenuItem {
            objectName: "canopyMenuHelpApplications"
            text: "Browse Applications"
            Accessible.name: "Browse installed applications"
            onTriggered: shellMenus.showLauncherRequested()
        }
        MenuItem {
            objectName: "canopyMenuHelpAbout"
            text: "About Canopy Classic"
            Accessible.name: "About Canopy Classic"
            onTriggered: shellMenus.aboutRequested()
        }
    }
}
