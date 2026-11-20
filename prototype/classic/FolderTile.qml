import QtQuick
import QtQuick.Controls

// Original lightweight folder artwork used by the visual-only Files preview.
Button {
    id: folder
    objectName: "canopyFolderTile"
    required property string folderName
    required property color folderTone
    property bool selected: false
    width: 108
    height: 84
    implicitWidth: 108
    implicitHeight: 84
    hoverEnabled: true
    padding: 0
    Accessible.name: folderName + " sample folder"
    Accessible.description: "Selects a sample tile without reading files from disk"

    background: Rectangle {
        radius: 9
        color: folder.selected ? "#e6f0fb"
              : folder.hovered ? "#f1f6fc" : "transparent"
        border.color: folder.selected ? "#a8c4e1" : "transparent"
        border.width: 1
    }
    contentItem: Item {
        Rectangle {
            id: folderBody
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 11
            width: 67
            height: 44
            radius: 7
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.lighter(folder.folderTone, 1.26) }
                GradientStop { position: 1; color: folder.folderTone }
            }
            border.color: Qt.darker(folder.folderTone, 1.14)
            border.width: 1
            Rectangle {
                x: 5
                y: -5
                width: 25
                height: 8
                radius: 3
                color: Qt.lighter(folder.folderTone, 1.18)
            }
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                anchors.top: parent.top
                anchors.topMargin: 8
                height: 22
                radius: 4
                color: "#66ffffff"
            }
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 5
                height: 1
                color: "#66ffffff"
            }
        }
        Label {
            anchors.top: folderBody.bottom
            anchors.topMargin: 7
            anchors.horizontalCenter: parent.horizontalCenter
            text: folder.folderName
            color: "#34465c"
            font.pixelSize: 11
            font.weight: folder.selected ? Font.DemiBold : Font.Normal
        }
    }
}
