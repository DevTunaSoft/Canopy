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
    signal activated(string applicationName)
    // Approved icon bytes are verified first, then drawn into a single
    // cached rounded-alpha image with a consistent inset and full-image fit.
    // This avoids square corners and keeps all imagery within the card.
    readonly property string iconUrl: canopyApprovedMode
        ? "image://canopy-dock/" + iconName.toLowerCase()
        : "qrc:/Canopy/Classic/assets/icons/"
          + iconName.toLowerCase() + ".svg"
    readonly property bool roundedArtActive: canopyApprovedMode
    readonly property bool iconReady: iconArt.status === Image.Ready
    width: 70
    height: 82
    implicitWidth: 70
    implicitHeight: 82
    padding: 0
    hoverEnabled: true
    onClicked: tile.activated(tile.iconName)
    Accessible.name: iconName + " preview"
    Accessible.description: "Original demonstration artwork, not a working app launcher"
    ToolTip.visible: hovered
    ToolTip.text: iconName === "Files" ? "Toggle Files preview" : iconName + " — preview only"
    background: Item {
        Rectangle {
            // Align the hover/focus halo with the icon, not the top of
            // the tall (70px) button. Keep an equal visual gap on both
            // sides of the 88px dock, at every tested resolution.
            anchors.centerIn: parent
            width: 68
            height: 68
            radius: 20
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
            anchors.centerIn: parent
            // Larger 66px icon display inside the 82px dock tile leaves
            // 8px above and below. All eight are scaled uniformly;
            // original master images and five-only artwork offsets remain untouched.
            width: 66
            height: 66
            source: tile.iconUrl
            sourceSize: Qt.size(192, 192)
            fillMode: Image.PreserveAspectFit
            asynchronous: false
            cache: true
            smooth: true
            Accessible.name: tile.iconName + " original dock artwork"
        }
    }
}
