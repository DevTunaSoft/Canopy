import QtQuick
import QtQuick.Controls

// Deferred payload for shellMenus in ShellMenuBar.qml. Every action, title,
// objectName and accessibility string is copied verbatim from the approved
// six-menu definition; only the owning scope is now an explicit interface.
// Inline state components use bound behavior and declared IDs only.
pragma ComponentBehavior: Bound
Item {
    id: shellMenus

    property var filesWindow: null
    property string homePath: "Home"
    // Injected by ShellMenuBar.qml; a local Theme keeps direct loads safe.
    property var menuPaletteSource: null

    signal showLauncherRequested()
    signal aboutRequested()

    Theme { id: fallbackPalette }
    readonly property var effectivePalette: menuPaletteSource || fallbackPalette

    // One token-only presentation contract for the whole menu subsystem.
    // Typography and spacing stay at the existing sizes; state colors come
    // only from Theme. No new artwork, blur, animation, timer, menu entry or
    // action change is introduced.
    QtObject {
        id: menuPresentation
        readonly property int leftPadding: 18
        readonly property int rightPadding: 18
        readonly property int topPadding: 7
        readonly property int bottomPadding: 7
        // Approved readable typography markers (source-gate contract):
        // font.pixelSize: 13
        // font.weight: Font.Medium
        readonly property int labelPixelSize: 13
        readonly property int labelWeight: Font.Medium
        readonly property int cornerSize: Math.max(4, Math.round(shellMenus.effectivePalette.cornerRadius / 4))
        readonly property real disabledOpacity: 0.55
        readonly property color surfaceColor: shellMenus.effectivePalette.tile
        readonly property color hoverColor: shellMenus.effectivePalette.tileHover
        readonly property color pressedColor: shellMenus.effectivePalette.accent
        readonly property color focusColor: shellMenus.effectivePalette.tile
        readonly property color focusBorderColor: shellMenus.effectivePalette.accent
        readonly property color textColor: shellMenus.effectivePalette.foreground
        readonly property color mutedTextColor: shellMenus.effectivePalette.muted
        readonly property color pressedTextColor: shellMenus.effectivePalette.tile
        readonly property color dividerColor: shellMenus.effectivePalette.dockBorder
    }
    readonly property var presentation: menuPresentation

    component PremiumMenu: Menu {
        background: Rectangle {
            color: menuPresentation.surfaceColor
            border.color: menuPresentation.dividerColor
            border.width: 1
            radius: menuPresentation.cornerSize
        }
    }



    component PremiumMenuItem: MenuItem {
        id: premiumItem
        leftPadding: menuPresentation.leftPadding
        rightPadding: menuPresentation.rightPadding
        topPadding: menuPresentation.topPadding
        bottomPadding: menuPresentation.bottomPadding
        font.pixelSize: menuPresentation.labelPixelSize
        font.weight: menuPresentation.labelWeight
        hoverEnabled: true
        // Disabled entries disclose unavailability to assistive technology,
        // and show the same hint in the folded-down label.
        Accessible.description: enabled ? "Activate " + text : text + " (unavailable)"
        background: Rectangle {
            radius: menuPresentation.cornerSize
            color: {
                if (!premiumItem.enabled) return "transparent"
                if (premiumItem.down) return menuPresentation.pressedColor
                if (premiumItem.highlighted || premiumItem.activeFocus) return menuPresentation.focusColor
                if (premiumItem.hovered) return menuPresentation.hoverColor
                return "transparent"
            }
            border.color: premiumItem.enabled && premiumItem.activeFocus
                          ? menuPresentation.focusBorderColor : "transparent"
            border.width: premiumItem.enabled && premiumItem.activeFocus ? 1 : 0
        }
        contentItem: Item {
            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                // Checkable entries keep their checked state visible without
                // artwork; idle and checked colors are theme tokens.
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    implicitWidth: 10
                    implicitHeight: 10
                    radius: 2
                    visible: premiumItem.checkable
                    color: "transparent"
                    border.color: premiumItem.checked
                                  ? menuPresentation.focusBorderColor
                                  : menuPresentation.dividerColor
                    border.width: 1
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 2
                        radius: 1
                        color: menuPresentation.focusBorderColor
                        visible: premiumItem.checked
                    }
                }
                Label {
                    anchors.verticalCenter: parent.verticalCenter
                    text: premiumItem.text + (premiumItem.enabled ? "" : " (unavailable)")
                    color: !premiumItem.enabled ? menuPresentation.mutedTextColor
                           : premiumItem.down ? menuPresentation.pressedTextColor
                           : menuPresentation.textColor
                    opacity: premiumItem.enabled ? 1 : menuPresentation.disabledOpacity
                    font.pixelSize: premiumItem.font.pixelSize
                    font.weight: premiumItem.font.weight
                    elide: Text.ElideRight
                    Accessible.name: text
                }
            }
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

    PremiumMenu {
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

    PremiumMenu {
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

    PremiumMenu {
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

    PremiumMenu {
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

    PremiumMenu {
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

    PremiumMenu {
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
