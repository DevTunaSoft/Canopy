import QtQuick
import QtQuick.Controls

// Classic's opt-in application catalogue. Native launch goes through the
// host-owned GIO bridge; no copied launch code, network or added art assets.
FocusScope {
    id: launcher
    objectName: "canopyApplicationLauncher"
    property bool approvedMode: false
    // Experimental optical corrections belong ONLY to this overlay.
    // The established dock uses image://canopy-dock/ and is never reframed.
    property bool framingReviewMode: false
    property bool opened: false
    property alias searchQuery: searchField.text
    property string selectionMessage: ""
    readonly property var applications: approvedMode
        ? [
            { title: "Browser" }, { title: "Mail" },
            { title: "Files" }, { title: "Calendar" },
            { title: "Photos" }, { title: "Music" },
            { title: "Terminal" }, { title: "Settings" }
          ]
        : [
            { title: "Files" }, { title: "Browser" },
            { title: "Settings" }, { title: "Photos" },
            { title: "Terminal" }, { title: "Trash" }
          ]
    readonly property var filteredApps: applications.filter(function(app) {
        return app.title.toLowerCase().indexOf(searchQuery.toLowerCase().trim()) >= 0
    })
    readonly property int catalogCount: applications.length
    readonly property int filteredCount: filteredApps.length
    // Availability comes from the host bridge, never from a local guess.
    signal applicationSelected(string applicationName)

    function isInstalled(name) {
        return canopySystemLaunchEnabled && canopySystemLauncher.canLaunch(name)
    }

    visible: opened
    focus: opened
    Keys.onEscapePressed: closeLauncher()

    function openLauncher() {
        searchField.text = ""
        selectionMessage = ""
        opened = true
        searchField.forceActiveFocus()
    }
    function closeLauncher() {
        opened = false
        searchField.text = ""
    }
    function toggleLauncher() {
        if (opened) closeLauncher()
        else openLauncher()
    }
    function choose(name) {
        // Opt-in native launch runs first. A failed launch never claims success.
        if (canopySystemLaunchEnabled && canopySystemLauncher.launch(name)) {
            closeLauncher()
            return
        }
        applicationSelected(name)
        if (name === "Files") {
            closeLauncher()
            return
        }
        selectionMessage = name + " is not connected in this preview"
        // Distinguish an installed app that failed from one not present.
        if (isInstalled(name))
            selectionMessage = name + " could not be launched"
    }

    Rectangle {
        anchors.fill: parent
        color: "#690d1a2b"
        MouseArea {
            anchors.fill: parent
            onClicked: launcher.closeLauncher()
        }
    }

    Rectangle {
        id: panel
        objectName: "canopyLauncherPanel"
        width: Math.min(parent.width - 42, 814)
        height: Math.min(parent.height - 106, 465)
        anchors.centerIn: parent
        radius: 22
        color: "#f3f8fc"
        border.width: 1
        border.color: "#b7d0dce8"
        clip: true

        Label {
            id: heading
            anchors.top: parent.top
            anchors.topMargin: 20
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Applications"
            color: "#2b3e52"
            font.pixelSize: 19
            font.weight: Font.DemiBold
        }
        TextField {
            id: searchField
            objectName: "canopyLauncherSearch"
            anchors.top: heading.bottom
            anchors.topMargin: 16
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width - 42, 590)
            height: 42
            placeholderText: "Find an application"
            font.pixelSize: 15
            color: "#263a4f"
            selectByMouse: true
            Accessible.name: "Search available preview applications"
            background: Rectangle {
                radius: 12
                color: "#ffffff"
                border.width: 1
                border.color: searchField.activeFocus ? "#5c8fb8" : "#cad7e2"
            }
            Keys.onEscapePressed: launcher.closeLauncher()
            Keys.onDownPressed: {
                if (grid.count > 0) {
                    grid.currentIndex = 0
                    grid.forceActiveFocus()
                }
            }
            Keys.onReturnPressed: {
                if (launcher.filteredCount > 0)
                    launcher.choose(launcher.filteredApps[0].title)
            }
        }
        GridView {
            id: grid
            objectName: "canopyLauncherGrid"
            anchors.top: searchField.bottom
            anchors.topMargin: 16
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: keyHints.top
            anchors.leftMargin: 21
            anchors.rightMargin: 21
            anchors.bottomMargin: 6
            clip: true
            model: launcher.filteredApps
            readonly property int columns: width < 470 ? 3 : 4
            cellWidth: width / columns
            cellHeight: panel.height < 410 ? 98 : 116
            keyNavigationWraps: true
            activeFocusOnTab: true
            delegate: Button {
                id: appButton
                objectName: "canopyLauncherAppButton"
                required property var modelData
                required property int index
                width: grid.cellWidth
                height: grid.cellHeight
                padding: 0
                hoverEnabled: true
                Accessible.name: "Select " + modelData.title
                Accessible.description: launcher.isInstalled(modelData.title)
                        ? "Launches with the system application bridge"
                        : "Not installed on this system"
                ToolTip.visible: hovered
                ToolTip.text: modelData.title
                onClicked: launcher.choose(modelData.title)
                background: Rectangle {
                    anchors.margins: 4
                    radius: 15
                    // Hover previews; keyboard focus and grid selection share
                    // the already-approved focus accent so the active tile is
                    // unmistakable without introducing a new colour.
                    color: appButton.hovered || appButton.activeFocus ||
                           (grid.activeFocus && grid.currentIndex === appButton.index)
                           ? "#dceaf5" : "transparent"
                    border.width: appButton.activeFocus ||
                                  (grid.activeFocus && grid.currentIndex === appButton.index)
                                  ? 2 : 0
                    border.color: "#5687b3"
                }
                contentItem: Column {
                    anchors.centerIn: parent
                    spacing: 7
                    Image {
                        objectName: "canopyLauncherIcon"
                        readonly property bool imageReady: status === Image.Ready
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 54
                        height: 54
                        source: launcher.approvedMode
                                ? (launcher.framingReviewMode
                                   ? "image://canopy-launcher-review/"
                                   : "image://canopy-dock/") + appButton.modelData.title.toLowerCase()
                                : "qrc:/Canopy/Classic/assets/icons/"
                                  + appButton.modelData.title.toLowerCase() + ".svg"
                        sourceSize: Qt.size(192, 192)
                        fillMode: Image.PreserveAspectFit
                        asynchronous: false
                        smooth: true
                        cache: true
                    }
                    Label {
                        width: appButton.width - 8
                        text: appButton.modelData.title
                        color: "#2c4055"
                        font.pixelSize: 13
                        font.weight: Font.Medium
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                }
            }
            Keys.onEscapePressed: launcher.closeLauncher()
            Keys.onReturnPressed: {
                if (currentIndex >= 0 && currentIndex < launcher.filteredCount)
                    launcher.choose(launcher.filteredApps[currentIndex].title)
            }
            Keys.onUpPressed: {
                if (currentIndex < grid.columns)
                    searchField.forceActiveFocus()
            }
            Keys.onBacktabPressed: searchField.forceActiveFocus()
        }
        // Static, single-line discoverability strip. Reuses the status colour
        // and the existing middle-dot separator; no timer, effect or artwork.
        Label {
            id: keyHints
            objectName: "canopyLauncherKeyHints"
            anchors.bottom: footer.top
            anchors.bottomMargin: 3
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 36
            height: 16
            text: "Up/Down select · Enter open · Esc close"
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            color: "#657b90"
            font.pixelSize: 11
            Accessible.name: "Launcher keyboard shortcuts: " + text
        }
        Label {
            id: footer
            objectName: "canopyLauncherStatus"
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 16
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 36
            height: 20
            text: launcher.selectionMessage.length > 0 ? launcher.selectionMessage :
                  launcher.filteredCount === 0 ? "No matching applications" :
                  canopySystemLaunchEnabled
                  ? "Select an installed application to launch"
                  : "Files opens the in-preview window · native launch is opt-in"
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            color: "#657b90"
            font.pixelSize: 11
        }
    }
}
