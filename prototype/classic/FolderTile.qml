import QtQuick
import QtQuick.Controls

// Files folder tile: reuse the SAME authored Canopy folder artwork
// for each folder, as a normal file manager does. Avoid the
// rejected random pastel folder treatment. Activation is delegated to the
// Files window's native, home-scoped browser; the tile only renders artwork.
Button {
    id: folder
    objectName: "canopyFolderTile"
    required property string folderName
    required property color folderTone // Legacy demo model input; not an icon tint.
    property bool selected: false
    // Compact only the Files sample grid; approved dock artwork is untouched.
    property bool compact: false
    readonly property bool imageReady: folderIcon.status === Image.Ready
    width: 108
    height: compact ? 68 : 90
    implicitWidth: 108
    implicitHeight: compact ? 68 : 90
    hoverEnabled: true
    padding: 0
    Accessible.name: folderName + " sample folder"
    Accessible.description: "Opens this folder in the Files browser when available"
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
            anchors.topMargin: folder.compact ? 0 : 4
            anchors.horizontalCenter: parent.horizontalCenter
            width: folder.compact ? 64 : 72
            height: folder.compact ? 50 : 64
            source: "qrc:/Canopy/Classic/assets/ui/folder-blue.svg"
            sourceSize: Qt.size(128, 128)
            fillMode: Image.PreserveAspectFit
            cache: true
            asynchronous: false
            smooth: true
        }
        Label {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: folder.compact ? 2 : 4
            anchors.horizontalCenter: parent.horizontalCenter
            text: folder.folderName
            color: "#34465c"
            font.pixelSize: folder.compact ? 10 : 11
            font.weight: folder.selected ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
        }
    }
}
