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
    readonly property bool compactLayout: width < 900

    // Original static artwork; no rotating placeholder rectangles.
    Wallpaper { anchors.fill: parent }

    // Visual-only composition: file management and window controls are not wired.
    // It scales down for screenshot checks; the floating dock remains unobscured.
    PreviewWindow {
        id: filesPreview
        width: Math.min(root.width - 72, Math.max(780, root.width * 0.56))
        height: Math.min(root.height - canopyTheme.barHeight - 166, Math.max(420, root.height * 0.56))
        x: Math.max(24, (root.width - width) / 2)
        y: canopyTheme.barHeight + Math.max(30, (root.height - canopyTheme.barHeight - canopyTheme.dockSize - height) / 2 - 10)
    }

    Rectangle {
        id: topBar
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
                Accessible.name: "Canopy penguin launcher placeholder"
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
                text: "Files"
                color: canopyTheme.foreground
                font.pixelSize: 13
                font.weight: Font.DemiBold
                font.family: "Sans Serif"
            }

            // Actual menu actions target only this standalone demo. No false
            // desktop/system integration is implied by these controls.
            Repeater {
                model: ["File", "Edit", "View", "Go", "Window", "Help"]
                delegate: Button {
                    id: topMenuButton
                    required property string modelData
                    visible: !root.compactLayout
                             || (modelData !== "Window" && modelData !== "Help")
                    text: modelData
                    hoverEnabled: true
                    Layout.preferredHeight: 27
                    padding: 6
                    font.pixelSize: 12
                    Accessible.name: modelData + " demo menu"
                    onClicked: actionMenu.open()
                    background: Rectangle {
                        radius: 5
                        color: topMenuButton.hovered || actionMenu.visible
                               ? "#38ffffff" : "transparent"
                    }
                    contentItem: Label {
                        text: topMenuButton.text
                        color: "#273345"
                        font.pixelSize: 12
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Menu {
                        id: actionMenu
                        MenuItem {
                            text: topMenuButton.modelData === "Help"
                                  ? "About this preview"
                                  : topMenuButton.modelData === "Edit"
                                  ? "Clear selection"
                                  : topMenuButton.modelData === "View"
                                  ? "Toggle Files window"
                                  : "Show Files preview"
                            onTriggered: {
                                if (topMenuButton.modelData === "Help") {
                                    aboutPopup.open()
                                } else if (topMenuButton.modelData === "Edit") {
                                    filesPreview.selectedFolder = ""
                                } else if (topMenuButton.modelData === "View") {
                                    filesPreview.visible = !filesPreview.visible
                                } else {
                                    filesPreview.visible = true
                                    filesPreview.currentSection = "Home"
                                }
                            }
                        }
                        MenuItem {
                            text: "Reset demo view"
                            onTriggered: {
                                filesPreview.visible = true
                                filesPreview.currentSection = "Home"
                                filesPreview.selectedFolder = ""
                            }
                        }
                    }
                }
            }
            Item { Layout.fillWidth: true }
            Label {
                text: Qt.formatDateTime(new Date(), "ddd d MMM")
                color: canopyTheme.foreground
                font.pixelSize: 12
                font.weight: Font.Medium
            }
        }
    }

    Dialog {
        id: aboutPopup
        title: "Canopy Classic Preview"
        modal: false
        anchors.centerIn: parent
        width: 360
        height: 185
        standardButtons: Dialog.Ok
        contentItem: Item {
            implicitWidth: 290
            implicitHeight: 68
            Label {
                anchors.fill: parent
                text: "A standalone design experiment. App launching and real file browsing are not implemented."
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                color: "#31475e"
            }
        }
    }

    // Dock controls are explicitly nonfunctional until session services exist.
    Rectangle {
        id: dock
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
                model: [
                    { title: "Home" },
                    { title: "Files" },
                    { title: "Browser" },
                    { title: "Photos" },
                    { title: "Mail" },
                    { title: "Calendar" },
                    { title: "Settings" }
                ]
                delegate: DockTile {
                    required property var modelData
                    iconName: modelData.title
                    previewActive: modelData.title === "Files"
                }
            }
        }
    }

}
