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
    // The approved illustration slot stays exactly 54px: the compiled
    // geometry self-test bounds it to 50..56px and the v3 five-icon pack is
    // SHA-locked at that presentation size. The *interaction plate* is a
    // separate 62px square (54 + 4px on each side) so hover/focus framing is
    // identical for every tile and matches the 62x62 optical crop used by
    // the frozen-five evidence. Nothing here resamples approved artwork.
    readonly property int artSize: 54
    readonly property int presentationSize: 62
    readonly property int presentationRadius: 18
    width: 58
    height: 70
    implicitWidth: 58
    implicitHeight: 70
    padding: 0
    hoverEnabled: true
    onClicked: tile.activated(tile.iconName)
    Accessible.name: iconName + " preview"
    Accessible.description: "Original demonstration artwork, not a working app launcher"
    ToolTip.visible: hovered
    ToolTip.text: iconName === "Files" ? "Toggle Files preview" : iconName + " — preview only"
    background: Item {
        Rectangle {
            // Align the hover/focus plate with the 54px art, not the top of
            // the tall (70px) button. The 62px square is the single
            // presentation size for all eight tiles, leaving an equal 4px
            // ring around every approved icon at every tested resolution.
            // Contrast was raised one step over the old 0x18/0x30 plates so
            // the interaction state remains visible on the pale dock plate;
            // this is interaction chrome only and never samples or recolors
            // the SHA-locked artwork.
            anchors.centerIn: parent
            width: tile.presentationSize
            height: tile.presentationSize
            radius: tile.presentationRadius
            visible: tile.hovered || tile.activeFocus
            color: tile.hovered ? "#3dffffff" : "#24ffffff"
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
            // A centered 54px image inside a 70px dock tile leaves 8px
            // on top and bottom. The old topMargin: 2 pushed every icon
            // visually high, despite having correct rounded corners.
            width: tile.artSize
            height: tile.artSize
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
