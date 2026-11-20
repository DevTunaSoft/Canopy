import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Preview-only file browser composition. This is not a live file manager.
Rectangle {
    id: preview
    objectName: "canopyPreviewWindow"
    property bool compact: width < 620
    radius: 20
    color: "#eeeafa"
    border.width: 1
    border.color: "#a8a5c8"
    clip: true
    Accessible.name: "Files window visual preview, not a functional file manager"

    Rectangle {
        id: titlebar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 53
        radius: 20
        color: "#e1dff3"
        // Fill the lower radius to keep a flat join with the content area.
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 24
            color: "#e1dff3"
        }
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
        color: "#dbd8ee"
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
                    color: modelData === "Home" ? "#bbb9e0" : "transparent"
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

        // Static toolbar composition. Navigation and search are deliberately
        // noninteractive until an actual file-management backend is connected.
        Rectangle {
            id: contentToolbar
            objectName: "canopyFilesToolbar"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 48
            color: "#eeecfa"
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: "#e1e7ee"
            }
            Row {
                anchors.left: parent.left
                anchors.leftMargin: preview.compact ? 14 : 22
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12
                Label {
                    text: "‹"
                    color: "#53677d"
                    font.pixelSize: 25
                    Accessible.name: "Back navigation preview, not interactive"
                }
                Label {
                    text: "›"
                    color: "#a5b1bf"
                    font.pixelSize: 25
                    Accessible.name: "Forward navigation preview, not interactive"
                }
                Rectangle {
                    width: 1
                    height: 18
                    color: "#d7e0e9"
                    anchors.verticalCenter: parent.verticalCenter
                }
                Label {
                    text: "Home"
                    color: "#54677d"
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            Rectangle {
                visible: !preview.compact
                width: 154
                height: 28
                radius: 8
                color: "#f0f4f8"
                border.color: "#dde5ed"
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                Label {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: "⌕  Search"
                    color: "#8897a8"
                    font.pixelSize: 12
                }
            }
        }

        Label {
            id: heading
            text: "Home"
            font.pixelSize: 21
            font.weight: Font.DemiBold
            color: "#27374b"
            anchors.left: parent.left
            anchors.leftMargin: 22
            anchors.top: contentToolbar.bottom
            anchors.topMargin: 16
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
            columns: preview.compact ? 2 : 4
            columnSpacing: preview.compact ? 10 : 20
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
                    width: preview.compact ? 78 : 102
                    spacing: 7
                    Item {
                        width: 68
                        height: 51
                        anchors.horizontalCenter: parent.horizontalCenter
                        Rectangle {
                            x: 4
                            y: 1
                            width: 29
                            height: 14
                            radius: 4
                            color: "#82c8ff"
                        }
                        Rectangle {
                            x: 1
                            y: 9
                            width: 66
                            height: 40
                            radius: 7
                            gradient: Gradient {
                                GradientStop { position: 0; color: "#71c5fa" }
                                GradientStop { position: 0.53; color: "#2fa5f0" }
                                GradientStop { position: 1; color: "#167bce" }
                            }
                            border.color: "#478fca"
                            border.width: 1
                        }
                        Rectangle {
                            x: 5
                            y: 14
                            width: 58
                            height: 9
                            radius: 4
                            color: "#60ffffff"
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
