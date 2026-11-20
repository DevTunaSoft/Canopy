import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1200
    height: 750
    minimumWidth: 720
    minimumHeight: 480
    visible: true
    title: "Canopy Classic — Technology Spike"
    color: "#eef2f8"

    Theme { id: canopyTheme }
    readonly property var classicApps: [
        { name: "Browser", icon: "Browser" },
        { name: "Mail", icon: "Mail" },
        { name: "Files", icon: "Files" },
        { name: "Calendar", icon: "Calendar" },
        { name: "Photos", icon: "Photos" },
        { name: "Music", icon: "Music" },
        { name: "Terminal", icon: "Terminal" },
        { name: "Settings", icon: "Settings" }
    ]
    readonly property bool compactLayout: width < 900
    property bool launcherOpen: false
    function toggleLauncher() { launcherOpen = !launcherOpen; if (launcherOpen) appLauncher.clearAndFocus() }
    Shortcut { sequence: "Ctrl+Space"; onActivated: root.toggleLauncher() }

    // Original abstract wallpaper: cached image, never a live effect or service.
    Landscape {
        anchors.fill: parent
    }

    // Two flat, static penumbra layers. No blur, ShaderEffect, particles,
    // animation or separate texture. A modest depth cue even on software Qt.
    Rectangle {
        anchors.fill: filesPreview
        anchors.leftMargin: -7
        anchors.rightMargin: -7
        anchors.topMargin: -4
        anchors.bottomMargin: -10
        radius: 18
        color: "#16344759"
        visible: !root.launcherOpen
        z: 0.1
    }
    Rectangle {
        anchors.fill: filesPreview
        anchors.leftMargin: -3
        anchors.rightMargin: -3
        anchors.topMargin: -2
        anchors.bottomMargin: -5
        radius: 16
        color: "#16344759"
        visible: !root.launcherOpen
        z: 0.2
    }

    // Visual-only composition: file management and window controls are not wired.
    // It scales down for screenshot checks; the floating dock remains unobscured.
    PreviewWindow {
        id: filesPreview
        visible: !root.launcherOpen
        z: 0.3
        width: Math.min(root.width - 72, 780)
        height: Math.min(root.height - canopyTheme.barHeight - 132, 480)
        x: Math.max(24, (root.width - width) / 2)
        y: canopyTheme.barHeight + Math.max(30, (root.height - canopyTheme.barHeight - canopyTheme.dockSize - height) / 2 - 10)
    }

    Rectangle {
        id: topBar
        z: 1
        objectName: "canopyTopBar"
        anchors.top: parent.top
        width: parent.width
        height: canopyTheme.barHeight
        color: canopyTheme.chrome

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: "#c9d1da"
            opacity: 0.65
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: root.compactLayout ? 14 : 22
            anchors.rightMargin: root.compactLayout ? 14 : 22
            spacing: root.compactLayout ? 12 : 20

            // Original, stylized white penguin silhouette, not Apple artwork.
            Item {
                id: tuxMark
                objectName: "canopyLauncher"
                Layout.preferredWidth: 26
                Layout.preferredHeight: 30
                Layout.minimumWidth: 26
                Layout.minimumHeight: 30
                Accessible.name: "Open Canopy application launcher"
                MouseArea { anchors.fill: parent; onClicked: root.toggleLauncher() }
                // Original silhouette assembled from static vector primitives,
                // avoiding Qt Canvas paint-surface scaling differences.
                Rectangle {
                    x: 3
                    y: 1
                    width: 20
                    height: 27
                    radius: 10
                    color: "#34445d"
                }
                Rectangle {
                    x: 7
                    y: 12
                    width: 12
                    height: 15
                    radius: 6
                    color: "#f8fafc"
                }
                Rectangle {
                    x: 8
                    y: 8
                    width: 3
                    height: 3
                    radius: 1.5
                    color: "#f8fafc"
                }
                Rectangle {
                    x: 15
                    y: 8
                    width: 3
                    height: 3
                    radius: 1.5
                    color: "#f8fafc"
                }
                Rectangle {
                    x: 11
                    y: 12
                    width: 4
                    height: 4
                    radius: 1
                    rotation: 45
                    color: "#d7a268"
                }
            }
            Label {
                text: "Canopy"
                color: canopyTheme.menuForeground
                font.pixelSize: 14
                font.bold: true
                font.family: "Sans Serif"
            }
            Label {
                text: "File"
                visible: !root.compactLayout
                color: canopyTheme.menuForeground
                font.pixelSize: 13
            }
            Label {
                text: "Edit"
                visible: !root.compactLayout
                color: canopyTheme.menuForeground
                font.pixelSize: 13
            }
            Label {
                text: "View"
                visible: !root.compactLayout
                color: canopyTheme.menuForeground
                font.pixelSize: 13
            }
            Label {
                text: "Go"
                visible: !root.compactLayout
                color: canopyTheme.menuForeground
                font.pixelSize: 13
            }
            Label {
                text: "Window"
                visible: !root.compactLayout
                color: canopyTheme.menuForeground
                font.pixelSize: 13
            }
            Label {
                text: "Help"
                visible: !root.compactLayout
                color: canopyTheme.menuForeground
                font.pixelSize: 13
            }
            Item { Layout.fillWidth: true }
            Label {
                text: Qt.formatDateTime(new Date(), "ddd d MMM")
                color: canopyTheme.menuForeground
                font.pixelSize: 12
                font.weight: Font.Medium
            }
        }
    }

    // Real interactive launcher overlay; selection does NOT run processes.
    LauncherOverlay {
        id: appLauncher
        z: 0.9
        anchors.fill: parent
        applications: root.classicApps
        opened: root.launcherOpen
        onCloseRequested: root.launcherOpen = false
    }

    // Dock controls are explicitly nonfunctional until session services exist.
    Rectangle {
        id: dock
        z: 1
        objectName: "canopyDock"
        width: Math.min(root.width - 32, dockRow.implicitWidth + 2 * canopyTheme.dockPadding)
        height: canopyTheme.dockSize
        radius: canopyTheme.cornerRadius
        color: canopyTheme.dockSurface
        border.color: canopyTheme.dockBorder
        border.width: 1
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 22
        clip: true

        Row {
            id: dockRow
            anchors.centerIn: parent
            spacing: canopyTheme.dockSpacing
            Repeater {
                model: root.classicApps
                delegate: DockTile {
                    required property var modelData
                    iconName: modelData.icon
                    // App execution is deliberately unavailable in the visual prototype.
                    onClicked: {}
                }
            }
        }
    }

    Label {
        anchors.right: parent.right
        anchors.rightMargin: 21
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 9
        text: "CANOPY CLASSIC · PREVIEW"
        color: canopyTheme.muted
        opacity: 0.64
        font.pixelSize: 9
        font.letterSpacing: 2
        visible: root.width > 900
    }
}
