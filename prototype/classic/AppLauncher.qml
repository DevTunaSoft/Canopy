import QtQuick
import QtQuick.Controls

// A lightweight, keyboard-searchable launcher shell. All artwork comes from
// the same icon pipeline as the dock; no duplicated services, remote fetching,
// timers, blur shaders, or claims that unsupported apps can launch.
Item {
    id: launcher
    objectName: "canopyAppLauncher"
    visible: false
    focus: visible
    signal filesPreviewRequested()

    readonly property var applicationNames: canopyApprovedMode
        ? ["Browser", "Mail", "Files", "Calendar", "Photos",
           "Music", "Terminal", "Settings"]
        : ["Files", "Browser", "Settings", "Photos", "Terminal", "Trash"]
    readonly property var filteredNames: applicationNames.filter(function(name) {
        return name.toLowerCase().indexOf(searchField.text.trim().toLowerCase()) !== -1
    })
    readonly property int visibleIconCount: filteredNames.length
    property string feedback: ""

    function openLauncher() {
        feedback = ""
        searchField.text = ""
        visible = true
        searchField.forceActiveFocus()
    }
    function closeLauncher() {
        visible = false
        feedback = ""
        searchField.text = ""
    }
    function selectApp(name) {
        if (name === "Files") {
            closeLauncher()
            filesPreviewRequested()
        } else {
            feedback = name + " is not connected to a Linux application yet"
        }
    }

    Keys.onEscapePressed: launcher.closeLauncher()

    Rectangle {
        anchors.fill: parent
        color: "#290b101b"
        MouseArea {
            anchors.fill: parent
            onClicked: launcher.closeLauncher()
        }
    }

    Rectangle {
        id: panel
        objectName: "canopyLauncherPanel"
        width: Math.min(880, launcher.width - 36)
        height: Math.min(450, Math.max(295, launcher.height - 170))
        x: (launcher.width - width) / 2
        y: 32 + Math.max(0, (launcher.height - 142 - height) / 2)
        radius: 28
        border.width: 1
        border.color: "#80e2e7f0"
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#e43c414f" }
            GradientStop { position: 1.0; color: "#f0272932" }
        }
        // A second static highlight establishes glass depth without
        // GPU-expensive background blur or a continuously animated effect.
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 1
            height: 1
            radius: 1
            color: "#78ffffff"
        }

        TextField {
            id: searchField
            objectName: "canopyLauncherSearch"
            anchors.top: parent.top
            anchors.topMargin: panel.height < 360 ? 18 : 27
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(panel.width - 40, 560)
            height: 44
            placeholderText: "Search Applications…"
            color: "#fcfcfe"
            placeholderTextColor: "#c8d2e1"
            selectionColor: "#719fc7"
            font.pixelSize: 16
            leftPadding: 19
            rightPadding: 16
            selectByMouse: true
            Accessible.name: "Search applications in Canopy preview"
            Keys.onEscapePressed: launcher.closeLauncher()
            background: Rectangle {
                radius: 23
                color: "#34ffffff"
                border.width: searchField.activeFocus ? 1.5 : 1
                border.color: searchField.activeFocus ? "#b8e4fc" : "#65ffffff"
            }
        }

        // Center each row independently: a six-icon fallback, eight-icon
        // approved set, or a one-result search must all remain balanced.
        Column {
            id: appGrid
            objectName: "canopyLauncherGrid"
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(panel.width - 48, 720)
            y: Math.max(searchField.y + searchField.height + 18,
                        (panel.height - implicitHeight) / 2 + 20)
            spacing: panel.height < 360 ? 4 : 22

            Row {
                id: firstRow
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Math.min(24, Math.max(8, (appGrid.width - 520) / 3))
                Repeater {
                    model: launcher.filteredNames.slice(0, 4)
                    delegate: LauncherTile {
                        required property string modelData
                        iconName: modelData
                        width: Math.min(142, (appGrid.width - 3 * firstRow.spacing) / 4)
                        onActivated: function(name) { launcher.selectApp(name) }
                    }
                }
            }
            Row {
                id: secondRow
                visible: launcher.visibleIconCount > 4
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: firstRow.spacing
                Repeater {
                    model: launcher.filteredNames.slice(4)
                    delegate: LauncherTile {
                        required property string modelData
                        iconName: modelData
                        width: Math.min(142, (appGrid.width - 3 * secondRow.spacing) / 4)
                        onActivated: function(name) { launcher.selectApp(name) }
                    }
                }
            }
        }

        Label {
            anchors.centerIn: appGrid
            visible: launcher.visibleIconCount === 0
            text: "No matching applications"
            color: "#fafbff"
            font.pixelSize: 14
        }

        Label {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: panel.height < 360 ? 10 : 18
            anchors.horizontalCenter: parent.horizontalCenter
            width: panel.width - 38
            text: launcher.feedback.length > 0 ? launcher.feedback
                  : "Preview only · app launching is not yet connected"
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            color: "#c7d2df"
            font.pixelSize: 11
        }
    }
}
