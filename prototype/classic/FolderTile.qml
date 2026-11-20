import QtQuick
import QtQuick.Controls

// Files visual-only sample tile: reuse the SAME authored Canopy folder artwork
// for each folder, as a real desktop file manager normally does. Avoid the
// rejected random pastel folder treatment. No actual filesystem access.
Button {
    id: folder
    objectName: "canopyFolderTile"
    required property string folderName
    required property color folderTone // Legacy demo model input; not an icon tint.
    property bool selected: false
    readonly property bool imageReady: folderIcon.status === Image.Ready
    width: 108
    height: 90
    implicitWidth: 108
    implicitHeight: 90
    hoverEnabled: true
    padding: 0
    Accessible.name: folderName + " sample folder"
    Accessible.description: "Selects a sample item, no disk access"
    background: Rectangle {
        radius: 9
        color: folder.selected ? "#dcecfb"
              : folder.hovered ? "#f0f6fa" : "transparent"
        border.color: folder.selected ? "#a7c7e4" : "transparent"
        border.width: folder.selected ? 1 : 0
    }
    contentItem: Item {
        Image {
            id: folderIcon
            objectName: "canopyFolderArtwork"
            anchors.top: parent.top
            anchors.topMargin: 4
            anchors.horizontalCenter: parent.horizontalCenter
            width: 72
            height: 64
            source: "qrc:/Canopy/Classic/assets/icons/files.svg"
            sourceSize: Qt.size(128, 128)
            fillMode: Image.PreserveAspectFit
            cache: true
            asynchronous: false
            smooth: true
        }
        Label {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 4
            anchors.horizontalCenter: parent.horizontalCenter
            text: folder.folderName
            color: "#34465c"
            font.pixelSize: 11
            font.weight: folder.selected ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
        }
    }
}
