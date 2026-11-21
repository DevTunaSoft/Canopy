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
    // Deliberately small optical-review offsets in final 54px screen pixels.
    // The artwork in the verified original PNG crops is not uniformly
    // composed, even though the QML image boxes are geometrically centered.
    // This OPTIONAL preview moves the full cached image only; it does not
    // edit, regenerate, zoom or overwrite any of the eight source masters.
    // A visual review is still required before adopting these corrections.
    readonly property var opticalOffsets: ({
        "Browser": [1, 0],
        "Mail": [0, -1],
        "Files": [-1, -1],
        "Calendar": [-2, 1],
        "Photos": [0, -1],
        "Music": [0, 1],
        "Terminal": canopyTerminalRefinementMode ? [-1, 0] : [-2, 2],
        "Settings": [-2, 1]
    })
    readonly property real opticalOffsetX:
        canopyApprovedMode && canopyOpticalReviewMode
            ? (opticalOffsets[iconName] || [0, 0])[0] : 0
    readonly property real opticalOffsetY:
        canopyApprovedMode && canopyOpticalReviewMode
            ? (opticalOffsets[iconName] || [0, 0])[1] : 0
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
            // Align the hover/focus halo with the icon, not the top of
            // the tall (70px) button. Keep an equal visual gap on both
            // sides of the 88px dock, at every tested resolution.
            anchors.centerIn: parent
            width: 56
            height: 56
            radius: 16
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
            anchors.horizontalCenterOffset: tile.opticalOffsetX
            anchors.verticalCenterOffset: tile.opticalOffsetY
            // A centered 54px image inside a 70px dock tile leaves 8px
            // on top and bottom. The old topMargin: 2 pushed every icon
            // visually high, despite having correct rounded corners.
            width: 54
            height: 54
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
