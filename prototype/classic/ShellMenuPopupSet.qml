import QtQuick
import QtQuick.Controls

// Deferred payload for shellMenus in ShellMenuBar.qml. Every action, title,
// objectName and accessibility string is copied verbatim from the approved
// six-menu definition; only the owning scope is now an explicit interface.
Item {
    id: shellMenus

    property var filesWindow: null
    property string homePath: "Home"

    signal showLauncherRequested()
    signal aboutRequested()

    // One static typography and padding contract for all 15 actions.
    // No new artwork, blur, animation, timer, menu entry or action change.
    component PremiumMenuItem: MenuItem {
        leftPadding: 18
        rightPadding: 18
        topPadding: 7
        bottomPadding: 7
        font.pixelSize: 13
        font.weight: Font.Medium
        Accessible.description: enabled ? "Activate " + text : text + " (unavailable)"
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

    Menu {
        id: fileMenu
        objectName: "canopyMenuFile"
        title: "File"
        PremiumMenuItem {
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
        PremiumMenuItem {
            objectName: "canopyMenuFileClose"
            text: "Close Files"
            Accessible.name: "Close Files window"
            enabled: shellMenus.filesWindow && shellMenus.filesWindow.visible
            onTriggered: shellMenus.filesWindow.requestClose()
        }
        MenuSeparator {}
        PremiumMenuItem {
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
        PremiumMenuItem {
            objectName: "canopyMenuEditFind"
            text: "Find"
            Accessible.name: "Find in Files"
            onTriggered: shellMenus.filesWindow.setSearch("")
        }
        PremiumMenuItem {
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
        PremiumMenuItem {
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
        PremiumMenuItem {
            objectName: "canopyMenuViewFocusSearch"
            text: "Focus Search"
            Accessible.name: "Focus Files search field"
            onTriggered: shellMenus.filesWindow.setSearch(
                             shellMenus.filesWindow.searchQuery)
        }
        MenuSeparator {}
        PremiumMenuItem {
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
        PremiumMenuItem {
            objectName: "canopyMenuGoBack"
            text: "Back"
            Accessible.name: "Go back in Files"
            enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoBack
            onTriggered: shellMenus.filesWindow.goBack()
        }
        PremiumMenuItem {
            objectName: "canopyMenuGoUp"
            text: "Up"
            Accessible.name: "Go up in Files"
            enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoUp
            onTriggered: shellMenus.filesWindow.goUp()
        }
        MenuSeparator {}
        PremiumMenuItem {
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
        PremiumMenuItem {
            objectName: "canopyMenuWindowFiles"
            text: "Files"
            Accessible.name: "Bring Files window to front"
            checkable: true
            checked: shellMenus.filesWindow && shellMenus.filesWindow.visible
            onTriggered: shellMenus.filesWindow.visible = checked
        }
        MenuSeparator {}
        PremiumMenuItem {
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
        PremiumMenuItem {
            objectName: "canopyMenuHelpApplications"
            text: "Browse Applications"
            Accessible.name: "Browse installed applications"
            onTriggered: shellMenus.showLauncherRequested()
        }
        PremiumMenuItem {
            objectName: "canopyMenuHelpAbout"
            text: "About Canopy Classic"
            Accessible.name: "About Canopy Classic"
            onTriggered: shellMenus.aboutRequested()
        }
    }
}
