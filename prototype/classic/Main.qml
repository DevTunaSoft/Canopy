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
    // Trusted host flag for the explicit owner-icons preview. It is false at
    // every default startup; approved QML geometry and colours stay frozen.
    readonly property bool ownerIconsPreviewActive: typeof canopyOwnerIconsPreview !== "undefined" && canopyOwnerIconsPreview
    // Keep the resting desktop composition unchanged until explicitly opened.
    Shortcut {
        sequence: "Ctrl+Space"
        onActivated: appLauncher.toggleLauncher()
    }

    // Original static artwork; no rotating placeholder rectangles.
    Wallpaper { anchors.fill: parent }

    // Default desktop image is the SHA-locked approved alpine master. The
    // exact PNG is compiled into the binary by qt_add_resources, so the
    // installed executable needs no CWD path or separate asset install rule.
    // The host may still override it with a separately validated
    // --landscape-wallpaper or --approved-art-dir; only one Image is decoded.
    // tools/check_wallpaper.py enforces the exact approved bytes.
    readonly property string approvedMasterWallpaperQrcUrl:
        "qrc:/Canopy/Classic/assets/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
    readonly property string approvedMasterWallpaperSourceUrl:
        "file:prototype/classic/assets/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
    readonly property string approvedMasterWallpaperUrl: {
        const waveUrl = canopyApprovedWallpaperUrl.toString()
        const separator = waveUrl.lastIndexOf('/')
        if (canopyApprovedMode && separator >= 0)
            return waveUrl.substring(0, separator + 1) + "Canopy_Classic_Master_Wallpaper_1920x1080.png"
        // Compiled Main.qml resolves against qrc:. The CWD-relative fallback
        // is only for an uncompiled source-tree preview, and names the same
        // approved master — never a substitute or a legacy wave.
        const compiled = Qt.resolvedUrl("Main.qml").toString().startsWith("qrc:")
        return compiled ? approvedMasterWallpaperQrcUrl : approvedMasterWallpaperSourceUrl
    }
    Component.onCompleted: {
        let wallpaperItem = null
        for (let i = 0; i < contentItem.children.length; ++i) {
            if (contentItem.children[i].objectName === "canopyWallpaper") {
                wallpaperItem = contentItem.children[i]
                break
            }
        }
        if (!wallpaperItem) {
            console.error("CANOPY_WALLPAPER_FAIL: wallpaper component missing")
            return
        }
        for (let i = 0; i < wallpaperItem.children.length; ++i) {
            const child = wallpaperItem.children[i]
            if (child.objectName === "canopyWallpaperImage") {
                child.source = Qt.binding(function() {
                    return canopyLandscapeWallpaperUrl.length > 0
                        ? canopyLandscapeWallpaperUrl
                        : approvedMasterWallpaperUrl
                })
                return
            }
        }
        console.error("CANOPY_WALLPAPER_FAIL: wallpaper image missing")
    }

    // The Files window owns navigation state. Main only shows it and forwards
    // menu requests through its explicit interface. Geometry stays unchanged.
    PreviewWindow {
        id: filesPreview
        width: Math.min(root.width - 72, Math.max(780, root.width * 0.56))
        height: Math.min(root.height - canopyTheme.barHeight - 166, Math.max(420, root.height * 0.56))
        x: Math.max(24, (root.width - width) / 2)
        y: canopyTheme.barHeight + Math.max(30, (root.height - canopyTheme.barHeight - canopyTheme.dockSize - height) / 2 - 10)
        onClosed: filesPreview.visible = false
    }

    ShellMenuBar {
        id: shellMenus
        filesWindow: filesPreview
        onShowLauncherRequested: appLauncher.openLauncher()
        onAboutRequested: aboutPopup.open()
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
            // Slightly wider inset and calmer rhythm keep the approved bar
            // height and item ordering while giving small labels room to read.
            anchors.leftMargin: root.compactLayout ? 16 : 24
            anchors.rightMargin: root.compactLayout ? 16 : 24
            spacing: root.compactLayout ? 10 : 18

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
                Accessible.description: "Open the Canopy applications menu"
                ToolTip.text: "Canopy menu"
                ToolTip.visible: tuxMark.hovered || tuxMark.activeFocus
                onClicked: launcherMenu.open()
                background: Rectangle {
                    radius: 5
                    color: tuxMark.hovered || tuxMark.activeFocus || launcherMenu.visible
                           ? "#44565d5a" : "transparent"
                    border.color: "#f7f5eb"
                    border.width: tuxMark.activeFocus ? 1 : 0
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
                        text: "Browse applications"
                        onTriggered: appLauncher.openLauncher()
                    }
                    MenuItem {
                        text: "About Canopy Classic"
                        onTriggered: aboutPopup.open()
                    }
                    MenuItem {
                        text: "Show Files"
                        onTriggered: filesPreview.visible = true
                    }
                }
            }
            Label {
                text: "Files"
                color: "#f7f5eb"
                font.pixelSize: 13
                font.weight: Font.Medium
                font.family: "Sans Serif"
            }

            // Menu definitions live in ShellMenuBar. The buttons keep the
            // approved top-bar geometry and open the matching real menu.
            Repeater {
                model: ["File", "Edit", "View", "Go", "Window", "Help"]
                delegate: Button {
                    id: topMenuButton
                    required property string modelData
                    readonly property var actionMenu: shellMenus.menuFor(modelData)
                    visible: !root.compactLayout
                             || (modelData !== "Window" && modelData !== "Help")
                    text: modelData
                    hoverEnabled: true
                    Layout.preferredHeight: 27
                    padding: 6
                    font.pixelSize: 13
                    font.weight: Font.Medium
                    Accessible.name: modelData + " menu"
                    Accessible.description: "Open the " + modelData + " menu"
                    onClicked: actionMenu.open()
                    background: Rectangle {
                        radius: 5
                        color: topMenuButton.hovered || topMenuButton.activeFocus
                               || actionMenu.visible
                               ? "#38ffffff" : "transparent"
                        border.color: "#f7f5eb"
                        border.width: topMenuButton.activeFocus ? 1 : 0
                    }
                    contentItem: Label {
                        text: topMenuButton.text
                        color: "#f7f5eb"
                        font.pixelSize: topMenuButton.font.pixelSize
                        font.weight: Font.Medium
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }
            Item { Layout.fillWidth: true }
            ClockLabel {
                Layout.alignment: Qt.AlignVCenter
                Accessible.description: "Local date and time; refreshes once per minute"
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
                text: "A familiar desktop design preview. Files navigation and application launching run only inside this window."
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
        onActivated: filesPreview.requestClose()
    }
    Shortcut {
        objectName: "canopyFilesOpenShortcut"
        sequence: "Ctrl+Shift+F"
        enabled: !filesPreview.visible
        onActivated: filesPreview.visible = true
    }

    // Original-art application catalogue opens only on request. Native launch
    // stays opt-in through the host bridge; fallback keeps the local preview.
    LauncherOverlay {
        id: appLauncher
        anchors.fill: parent
        z: 20
        approvedMode: root.approvedAssetsActive
        framingReviewMode: canopyIconFramingReview
        onApplicationSelected: function(applicationName) {
            if (applicationName === "Files")
                filesPreview.visible = true
        }
    }

    // Notification centre is registered in the compiled shell but starts
    // hidden, so the approved resting desktop is byte-for-byte unchanged.
    // The controller is a trusted host boundary; the preview host reports
    // itself disconnected, so every opening shows a disclosure and no rows.
    NotificationCenter {
        id: notificationCenter
        anchors.fill: parent
        z: 101
        controller: typeof canopyNotificationSource !== "undefined"
                    ? canopyNotificationSource : null
    }

    // Local preview-window shortcut only: no global binding, no daemon.
    Shortcut {
        objectName: "canopyNotificationCenterShortcut"
        sequence: "Ctrl+Alt+N"
        onActivated: notificationCenter.toggleCenter()
    }

    // The Files dock tile toggles the preview; other tiles keep the approved
    // visual composition without claiming session-level actions.
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
                        if (applicationName === "Files") {
                            filesPreview.visible = !filesPreview.visible
                        }
                    }
                }
            }
        }
    }

}
