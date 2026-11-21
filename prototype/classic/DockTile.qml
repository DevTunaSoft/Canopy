import QtQuick
import QtQuick.Controls

// Artist-authored, original SVG per application. Icons are pre-rendered/cached
// by Qt's SVG image plugin; no Canvas paint loops, effects or animation timers.
// These tiles remain visual demos until app launching is really implemented.
Button {
    id: tile
    objectName: "canopyDockTile"
    required property string iconName
    property bool previewActive: false
    property int artworkPixels: 54  // 54 in dock; 62 in the app launcher
    readonly property string approvedFileName:
        iconName === "Browser" ? "Browser_Option_3.png" :
        iconName === "Mail" ? "Mail_Option_5.png" :
        iconName === "Files" ? "Files_Option_2.png" :
        iconName === "Calendar" ? "Calendar_Option_3.png" :
        iconName === "Photos" ? "Photos_Option_2.png" :
        iconName === "Music" ? "Music_Option_3.png" :
        iconName === "Terminal" ? "Terminal_Option_4.png" :
        iconName === "Settings" ? "Settings_Option_8.png" : ""
    readonly property string iconUrl: canopyApprovedMode
        ? canopyApprovedIconBase + approvedFileName
        : "qrc:/Canopy/Classic/assets/icons/"
          + iconName.toLowerCase() + ".svg"
    readonly property bool iconReady: iconArt.status === Image.Ready
    width: artworkPixels + 4
    height: artworkPixels + 16
    implicitWidth: artworkPixels + 4
    implicitHeight: artworkPixels + 16
    padding: 0
    hoverEnabled: true
    Accessible.name: iconName + " preview"
    Accessible.description: "Original demonstration artwork, not a working app launcher"
    ToolTip.visible: hovered
    ToolTip.text: iconName + " — preview only"
    background: Item {
        Rectangle {
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            width: tile.artworkPixels + 2
            height: tile.artworkPixels + 2
            radius: 13
            visible: tile.hovered || tile.activeFocus
            color: tile.hovered ? "#30ffffff" : "#18ffffff"
            border.color: tile.activeFocus ? "#aac9f2ff" : "transparent"
            border.width: tile.activeFocus ? 2 : 0
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
            width: 5
            height: 5
            radius: 2.5
            color: "#2f4f69"
            visible: tile.previewActive
        }
    }
    contentItem: Item {
        Image {
            id: iconArt
            objectName: "canopyDockIcon"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 2
            width: tile.artworkPixels
            height: tile.artworkPixels
            source: tile.iconUrl
            sourceSize: Qt.size(128, 128)
            fillMode: Image.PreserveAspectFit
            asynchronous: false
            cache: true
            smooth: true
            Accessible.name: tile.iconName + " original dock artwork"
        }
    }
}
