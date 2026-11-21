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
    readonly property bool approvedAssetsActive: canopyApprovedMode

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
        color: canopyApprovedMode ? "#995e89a9" : canopyTheme.chrome

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

            // User-requested full-color Tux: charcoal, white, amber and gold.
            // Retains the reference silhouette, never an Apple-owned logo.
            ToolButton {
                id: tuxMark
                objectName: "canopyLauncher"
                Layout.preferredWidth: 30
                Layout.preferredHeight: 29
                Layout.minimumWidth: 30
                Layout.minimumHeight: 29
                padding: 0
                Accessible.name: "Canopy penguin launcher"
                onClicked: launcherMenu.open()
                background: Rectangle {
                    radius: 5
                    color: tuxMark.hovered || launcherMenu.visible ? "#44565d5a" : "transparent"
                }
                contentItem: Image {
                    id: penguinArt
                    source: "qrc:/Canopy/Classic/assets/brand/penguin-launcher.svg"
                    sourceSize: Qt.size(128, 128)
                    fillMode: Image.PreserveAspectFit
                    cache: true
                    smooth: true
                }
                readonly property bool imageReady: penguinArt.status === Image.Ready
                Menu {
                    id: launcherMenu
                    MenuItem {
                        text: "About Canopy preview"
                        onTriggered: aboutPopup.open()
                    }
                    MenuItem {
                        text: "Show Files preview"
                        onTriggered: filesPreview.visible = true
                    }
                }
            }
            Label {
                text: "Files"
                color: "#f7f5eb"
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
                        color: "#f7f5eb"
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
                color: "#f7f5eb"
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
                text: canopySystemLaunchEnabled
                      ? "Canopy Classic preview with optional native Linux application launching. File browsing inside this sample window is not implemented."
                      : "A standalone design experiment. Native app launching is disabled; real file browsing is not implemented."
                wrapMode: Text.WordWrap
                font.pixelSize: 12
                color: "#31475e"
            }
        }
    }

    // Keyboard controls for this preview window; no global shortcuts or daemon.
    Shortcut {
        objectName: "canopyFilesCloseShortcut"
        sequence: "Ctrl+W"
        enabled: filesPreview.visible
        onActivated: filesPreview.visible = false
    }
    Shortcut {
        objectName: "canopyFilesOpenShortcut"
        sequence: "Ctrl+Shift+F"
        enabled: !filesPreview.visible
        onActivated: filesPreview.visible = true
    }

    // Default dock remains a visual preview. Native Linux app launching is
    // available only with the explicit --enable-system-apps opt-in.
    Rectangle {
        id: dock
        objectName: "canopyDock"
        width: Math.min(root.width - 32, dockRow.implicitWidth + 2 * canopyTheme.dockPadding)
        height: canopyTheme.dockSize
        radius: canopyTheme.cornerRadius
        color: canopyApprovedMode ? "#b0d6e8f6" : canopyTheme.dockSurface
        border.color: canopyApprovedMode ? "#e1faffff" : canopyTheme.dockBorder
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
                model: canopyApprovedMode
                    ? [
                        { title: "Browser" },
                        { title: "Mail" },
                        { title: "Files" },
                        { title: "Calendar" },
                        { title: "Photos" },
                        { title: "Music" },
                        { title: "Terminal" },
                        { title: "Settings" }
                    ]
                    : [
                        { title: "Files" },
                        { title: "Browser" },
                        { title: "Settings" },
                        { title: "Photos" },
                        { title: "Terminal" },
                        { title: "Trash" }
                    ]
                delegate: DockTile {
                    required property var modelData
                    iconName: modelData.title
                    previewActive: modelData.title === "Files" && filesPreview.visible
                    onActivated: function(applicationName) {
                        if (canopySystemLaunchEnabled) {
                            if (canopySystemLauncher.launch(applicationName))
                                return
                        }
                        if (applicationName === "Files")
                            filesPreview.visible = !filesPreview.visible
                    }
                }
            }
        }
    }

}
