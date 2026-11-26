import QtQuick
import QtQuick.Controls

// Minimal desktop context menu. This is a view only: it owns no service, no
// process, no shell command and no timer. It stays inert unless the trusted
// host opts in with --enable-desktop-context-menu, and every native action is
// delegated to the existing SystemAppLauncher through the host bridge.
Item {
    id: desktopContextMenu
    objectName: "canopyDesktopContextMenu"

    // The trusted host always registers this bridge before QML loads. The
    // typeof guard keeps a standalone QML preview fail-closed instead of
    // throwing when the host boundary is absent.
    readonly property var bridge: typeof canopyDesktopContextMenu !== "undefined"
                                  ? canopyDesktopContextMenu : null
    readonly property bool contextEnabled: bridge && bridge.enabled
    readonly property bool nativeAvailable: bridge && bridge.nativeAvailable
    readonly property string disclosure: bridge
                                          ? bridge.disclosure
                                          : "Unavailable — no native host bridge"
    property int topInset: 0
    property int bottomInset: 0
    readonly property bool menuVisible: contextMenu.visible

    signal openLauncherRequested()
    signal showFilesRequested()
    signal aboutRequested()

    function openAt(x, y) {
        if (!contextEnabled)
            return false
        contextMenu.popup(x, y)
        return true
    }

    function closeMenu() {
        contextMenu.close()
        return !contextMenu.visible
    }

    // Invisible right-click surface limited to the desktop area between the
    // approved top bar and dock. It is disabled by default, so the resting
    // composition and all existing interactions are unchanged.
    MouseArea {
        id: contextSurface
        objectName: "canopyDesktopContextSurface"
        anchors.fill: parent
        anchors.topMargin: desktopContextMenu.topInset
        anchors.bottomMargin: desktopContextMenu.bottomInset
        enabled: desktopContextMenu.contextEnabled
        acceptedButtons: Qt.RightButton
        hoverEnabled: false
        onClicked: {
            if (mouse.button === Qt.RightButton)
                desktopContextMenu.openAt(mouseX, contextSurface.y + mouseY)
        }
    }

    // One Qt-provided menu; no custom palette, artwork, geometry or panel
    // service. Native launching is offered only when the host reports it is
    // available; otherwise a disabled item discloses why.
    Menu {
        id: contextMenu
        objectName: "canopyDesktopContextMenuPopup"
        MenuItem {
            objectName: "canopyDesktopContextBrowse"
            text: "Browse applications"
            onTriggered: desktopContextMenu.openLauncherRequested()
        }
        MenuItem {
            objectName: "canopyDesktopContextFiles"
            text: "Show Files"
            onTriggered: desktopContextMenu.showFilesRequested()
        }
        MenuItem {
            objectName: "canopyDesktopContextAbout"
            text: "About Canopy Classic"
            onTriggered: desktopContextMenu.aboutRequested()
        }
        MenuItem {
            objectName: "canopyDesktopContextNative"
            text: "Open Terminal"
            enabled: desktopContextMenu.nativeAvailable
            onTriggered: {
                if (!desktopContextMenu.bridge
                        || !desktopContextMenu.bridge.openTerminal())
                    console.warn("CANOPY_DESKTOP_CONTEXT_NATIVE_REFUSED")
            }
        }
        MenuItem {
            objectName: "canopyDesktopContextDisclosure"
            enabled: false
            visible: !desktopContextMenu.nativeAvailable
            text: desktopContextMenu.disclosure
        }
    }
}
