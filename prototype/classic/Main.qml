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
    color: "#101b29"

    readonly property color foreground: "#f3f5f9"
    readonly property color surface: "#243449"
    readonly property color accent: "#91c5ff"
    readonly property bool compactLayout: width < 900

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#263d56" }
            GradientStop { position: 1; color: "#0c1420" }
        }
    }

    Rectangle {
        id: topBar
        anchors.top: parent.top
        width: parent.width
        height: 44
        color: "#e6192535"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            spacing: root.compactLayout ? 12 : 18
            Label {
                text: "◈"
                color: root.accent
                font.pixelSize: 22
                Accessible.name: "Canopy menu placeholder"
            }
            Label { text: "Canopy"; color: root.foreground; font.bold: true }
            Label { text: "File"; color: root.foreground; visible: !root.compactLayout }
            Label { text: "View"; color: root.foreground; visible: !root.compactLayout }
            Item { Layout.fillWidth: true }
            Label { text: Qt.formatDateTime(new Date(), "ddd d MMM"); color: root.foreground }
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 12
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Canopy"
            font.pixelSize: 54
            font.weight: Font.Light
            color: root.foreground
        }
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "The Familiar Feel. The Freedom of Linux."
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            width: Math.min(implicitWidth, root.width - 48)
            font.pixelSize: 15
            color: "#c2d1e4"
        }
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Technology spike · not a desktop session"
            font.pixelSize: 12
            color: "#9fb2c8"
        }
    }

    Rectangle {
        id: dock
        width: Math.min(root.width - 32, dockRow.implicitWidth + 28)
        height: 76
        radius: 22
        color: root.surface
        border.color: "#617c98"
        border.width: 1
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        clip: true

        Row {
            id: dockRow
            anchors.centerIn: parent
            spacing: 12
            Repeater {
                model: [
                    { title: "Home", glyph: "⌂" },
                    { title: "Search", glyph: "⌕" },
                    { title: "Files", glyph: "▤" },
                    { title: "Settings", glyph: "⚙" }
                ]
                delegate: Button {
                    required property var modelData
                    width: 56
                    height: 56
                    hoverEnabled: true
                    Accessible.name: modelData.title + " (demonstration)"
                    ToolTip.visible: hovered
                    ToolTip.text: modelData.title + " — demonstration only"
                    background: Rectangle {
                        radius: 14
                        color: parent.hovered ? "#46617e" : "#334b65"
                    }
                    contentItem: Label {
                        text: modelData.glyph
                        font.pixelSize: 28
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        color: root.foreground
                    }
                }
            }
        }
    }
}
