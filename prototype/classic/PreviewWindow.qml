import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Preview-only file browser composition. This is not a live file manager.
Rectangle {
    id: preview
    objectName: "canopyPreviewWindow"
    property bool compact: width < 620
    radius: 13
    color: "#fbfcfe"
    border.width: 1
    border.color: "#b9c5d2"
    clip: true
    Accessible.name: "Files window visual preview, not a functional file manager"

    Rectangle {
        id: titlebar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 53
        color: "#eef2f6"
        Row {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Repeater {
                model: ["#e7827a", "#e8bc65", "#78bf8c"]
                delegate: Rectangle {
                    required property string modelData
                    width: 12
                    height: 12
                    radius: 6
                    color: modelData
                    border.color: "#77818a"
                    border.width: 0.5
                }
            }
        }
        Label {
            anchors.centerIn: parent
            text: "Files"
            font.pixelSize: 13
            font.weight: Font.DemiBold
            color: "#455366"
        }
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: "#d9e0e8"
        }
    }

    Rectangle {
        id: sidebar
        anchors.left: parent.left
        anchors.top: titlebar.bottom
        anchors.bottom: parent.bottom
        width: preview.compact ? 126 : 180
        color: "#eaf0f6"
        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: "#d6dfe9"
        }
        Column {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 7
            Label {
                text: "FAVORITES"
                color: "#728398"
                font.pixelSize: 10
                font.weight: Font.DemiBold
                font.letterSpacing: 1.2
                bottomPadding: 8
            }
            Repeater {
                model: ["Home", "Documents", "Pictures", "Downloads"]
                delegate: Rectangle {
                    required property string modelData
                    width: parent.width
                    height: 32
                    radius: 7
                    color: modelData === "Home" ? "#d7e5f5" : "transparent"
                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: 9
                        spacing: 9
                        Rectangle {
                            width: 12
                            height: 12
                            radius: modelData === "Home" ? 3 : 2
                            color: modelData === "Home" ? "#598ac4" : "#93a6bc"
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData
                            font.pixelSize: 12
                            color: "#33465a"
                        }
                    }
                }
            }
        }
    }

    Item {
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: titlebar.bottom
        anchors.bottom: parent.bottom

        Label {
            id: heading
            text: "Home"
            font.pixelSize: 21
            font.weight: Font.DemiBold
            color: "#27374b"
            anchors.left: parent.left
            anchors.leftMargin: 22
            anchors.top: parent.top
            anchors.topMargin: 20
        }
        Label {
            id: subtitle
            text: "Your places"
            font.pixelSize: 12
            color: "#78899b"
            anchors.left: heading.left
            anchors.top: heading.bottom
            anchors.topMargin: 4
        }
        Grid {
            anchors.left: heading.left
            anchors.right: parent.right
            anchors.rightMargin: 18
            anchors.top: subtitle.bottom
            anchors.topMargin: 20
            columns: preview.compact ? 2 : 3
            columnSpacing: preview.compact ? 10 : 22
            rowSpacing: 17
            Repeater {
                model: [
                    { name: "Documents", tone: "#79a8d9" },
                    { name: "Pictures", tone: "#a59ad9" },
                    { name: "Music", tone: "#dfab7a" },
                    { name: "Projects", tone: "#8dbdb1" },
                    { name: "Downloads", tone: "#85a4d2" },
                    { name: "Shared", tone: "#c59db5" }
                ]
                delegate: Column {
                    required property var modelData
                    width: preview.compact ? 78 : 94
                    spacing: 7
                    Rectangle {
                        width: 64
                        height: 48
                        radius: 7
                        color: modelData.tone
                        border.color: "#a7b5c6"
                        border.width: 1
                        anchors.horizontalCenter: parent.horizontalCenter
                        Rectangle {
                            width: 24
                            height: 7
                            radius: 3
                            color: modelData.tone
                            anchors.top: parent.top
                            anchors.topMargin: -4
                            anchors.left: parent.left
                            anchors.leftMargin: 4
                        }
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 5
                            radius: 4
                            color: "#55ffffff"
                        }
                    }
                    Label {
                        text: modelData.name
                        font.pixelSize: 11
                        color: "#405269"
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }
            }
        }
    }
}
