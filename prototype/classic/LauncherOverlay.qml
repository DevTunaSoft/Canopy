import QtQuick
import QtQuick.Controls

// Classic's opt-in on-screen application catalogue, adapted from the prior
// launcher prototype. No process execution, network, daemon or added art assets.
FocusScope {
    id: launcher
    objectName: "canopyApplicationLauncher"
    property bool approvedMode: false
    property bool nativeAppLaunchEnabled: false
    // Experimental optical corrections belong ONLY to this overlay.
    // The established dock uses image://canopy-dock/ and is never reframed.
    property bool framingReviewMode: false
    property bool opened: false
    property alias searchQuery: searchField.text
    property string selectionMessage: ""
    // Populated only when the launcher opens with explicit native opt-in;
    // never poll the GIO database or change the resting desktop/dock.
    property var nativeAppAvailability: ({})
    property int nativeAvailableCount: 0
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
    signal applicationSelected(string applicationName)

    visible: opened
    focus: opened
    Keys.onEscapePressed: closeLauncher()

    function refreshNativeAvailability() {
        if (!nativeAppLaunchEnabled) {
            nativeAppAvailability = ({})
            nativeAvailableCount = 0
            return
        }
        const available = ({})
        let count = 0
        for (let i = 0; i < applications.length; i++) {
            const title = applications[i].title
            const installed = canopySystemLauncher.canLaunch(title)
            available[title] = installed
            if (installed)
                count++
        }
        nativeAppAvailability = available
        nativeAvailableCount = count
    }
    function openLauncher() {
        searchField.text = ""
        selectionMessage = ""
        // A newly installed app is discovered on the next open; there are
        // no timers, background monitors, permissions or disk scans in QML.
        refreshNativeAvailability()
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
        // Real Linux desktop launch is strictly opt-in. Names come only
        // from the fixed app catalogue; C++ GIO rechecks the exact allowlist
        // and never constructs a shell command or accepts arbitrary Exec.
        // The original dock remains completely unchanged.
        if (nativeAppLaunchEnabled && canopySystemLauncher.launch(name)) {
            closeLauncher()
            return
        }
        // Preserve the approved default demo interaction when native
        // services are disabled, unavailable or do not support a category.
        applicationSelected(name)
        if (name === "Files") {
            closeLauncher()
        } else {
            selectionMessage = nativeAppLaunchEnabled
                    ? name + " is not installed or could not start"
                    : name + " is not connected in this preview"
        }
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
            anchors.topMargin: 15
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width - 42, 590)
            height: 40
            placeholderText: "Find an application"
            font.pixelSize: 14
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
            anchors.topMargin: 14
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footer.top
            anchors.leftMargin: 21
            anchors.rightMargin: 21
            anchors.bottomMargin: 8
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
                Accessible.description: !launcher.nativeAppLaunchEnabled
                    ? "Application preview"
                    : launcher.nativeAppAvailability[modelData.title]
                      ? "Installed Linux application"
                      : modelData.title === "Files"
                        ? "Native Files unavailable; sample preview available"
                        : "No matching installed Linux application"
                ToolTip.visible: hovered
                ToolTip.text: modelData.title
                onClicked: launcher.choose(modelData.title)
                background: Rectangle {
                    anchors.margins: 4
                    radius: 15
                    color: appButton.hovered || appButton.activeFocus
                           ? "#dceaf5" : "transparent"
                    border.width: appButton.activeFocus ? 1 : 0
                    border.color: "#5687b3"
                }
                contentItem: Column {
                    anchors.centerIn: parent
                    spacing: 6
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
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                    Label {
                        objectName: "canopyLauncherNativeAppState"
                        visible: launcher.nativeAppLaunchEnabled
                        width: appButton.width - 8
                        text: launcher.nativeAppAvailability[appButton.modelData.title]
                              ? "Installed"
                              : appButton.modelData.title === "Files"
                                ? "Preview only" : "Not installed"
                        color: launcher.nativeAppAvailability[appButton.modelData.title]
                               ? "#2c7059" : "#66798b"
                        font.pixelSize: 10
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
            Keys.onBacktabPressed: searchField.forceActiveFocus()
        }
        Label {
            id: footer
            objectName: "canopyLauncherStatus"
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 15
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 36
            height: 19
            text: launcher.selectionMessage.length > 0 ? launcher.selectionMessage :
                  launcher.filteredCount === 0 ? "No matching applications" :
                  (launcher.nativeAppLaunchEnabled
                    ? launcher.nativeAvailableCount + " installed application categories · Files falls back to preview"
                    : "Files opens the sample window · others are preview-only")
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            color: "#657b90"
            font.pixelSize: 11
        }
    }
}
