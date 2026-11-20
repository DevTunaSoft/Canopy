import QtQuick
import QtQuick.Controls

// Interactive search and keyboard navigation, but no arbitrary process launch.
// Uses the original DockTile artwork until licensed high-detail assets are ready.
FocusScope {
    id: launcher
    objectName: "canopyApplicationLauncher"
    property bool opened: false
    visible: opened
    focus: opened
    signal closeRequested()
    property string selectionMessage: ""
    // Populated by Main.qml; one shared catalog prevents dock/launcher drift.
    property var applications: []
    readonly property var filteredApps: applications.filter(function(app) {
        return app.name.toLowerCase().indexOf(searchField.text.toLowerCase().trim()) !== -1
    })
    readonly property int resultCount: filteredApps.length
    function clearAndFocus() {
        searchField.text = ""
        selectionMessage = ""
        searchField.forceActiveFocus()
    }

    Rectangle {
        anchors.fill: parent
        color: "#79050922"
        MouseArea {
            anchors.fill: parent
            onClicked: launcher.closeRequested()
        }
    }
    Rectangle {
        id: panel
        objectName: "canopyLauncherPanel"
        width: Math.min(parent.width - 48, 824)
        height: Math.min(parent.height - 170, 405)
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -18
        radius: 28
        color: "#e42d2947"
        border.width: 1
        border.color: "#759da4c7"

        // Static, non-blurred glass-like layered surface.
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: 27
            color: "#132a3456"
        }
        TextField {
            id: searchField
            objectName: "canopyLauncherSearch"
            width: Math.min(parent.width - 48, 550)
            height: 42
            anchors.top: parent.top
            anchors.topMargin: 24
            anchors.horizontalCenter: parent.horizontalCenter
            placeholderText: "Search applications"
            color: "#ffffff"
            placeholderTextColor: "#c9cfdf"
            font.pixelSize: 15
            leftPadding: 18
            rightPadding: 18
            selectByMouse: true
            background: Rectangle {
                radius: 21
                color: "#60778098"
                border.color: searchField.activeFocus ? "#d9e9ff" : "#628ca2b6"
                border.width: 1
            }
            Keys.onEscapePressed: launcher.closeRequested()
            Keys.onDownPressed: {
                appGrid.currentIndex = appGrid.count > 0 ? 0 : -1
                appGrid.forceActiveFocus()
            }
            Keys.onReturnPressed: {
                if (appGrid.count > 0) {
                    appGrid.currentIndex = 0
                    launcher.selectionMessage = launcher.filteredApps[0].name + " — preview only"
                }
            }
        }

        GridView {
            id: appGrid
            objectName: "canopyLauncherGrid"
            anchors.top: searchField.bottom
            anchors.topMargin: 24
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footer.top
            anchors.leftMargin: 25
            anchors.rightMargin: 25
            anchors.bottomMargin: 10
            clip: true
            model: launcher.filteredApps
            readonly property int columnCount: width < 535 ? 3 : width < 700 ? 4 : 6
            cellWidth: width / columnCount
            cellHeight: panel.height < 360 ? 64 : 110
            keyNavigationWraps: true
            activeFocusOnTab: true
            highlightFollowsCurrentItem: true
            delegate: Item {
                required property var modelData
                required property int index
                width: appGrid.cellWidth
                height: appGrid.cellHeight
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 5
                    radius: 14
                    color: appGrid.activeFocus && appGrid.currentIndex === index ? "#365f85b6" : "transparent"
                }
                DockTile {
                    iconName: modelData.icon
                    anchors.top: parent.top
                    anchors.topMargin: panel.height < 360 ? 1 : 9
                    anchors.horizontalCenter: parent.horizontalCenter
                    onClicked: launcher.selectionMessage = modelData.name + " — preview only"
                }
                Label {
                    text: modelData.name
                    anchors.top: parent.top
                    anchors.topMargin: panel.height < 360 ? 50 : 66
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 10
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    color: "#f6f5ff"
                    font.pixelSize: 12
                }
            }
            Keys.onEscapePressed: launcher.closeRequested()
            Keys.onReturnPressed: {
                if (currentIndex >= 0 && currentIndex < launcher.filteredApps.length)
                    launcher.selectionMessage = launcher.filteredApps[currentIndex].name + " — preview only"
            }
            Keys.onBacktabPressed: searchField.forceActiveFocus()
        }
        Label {
            id: footer
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 14
            height: 22
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            text: launcher.selectionMessage.length ? launcher.selectionMessage :
                (launcher.filteredApps.length ? "Search and select · app launching not connected" : "No applications found")
            color: "#cdd4e4"
            font.pixelSize: 11
        }
    }
}
