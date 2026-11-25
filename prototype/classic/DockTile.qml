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
    // Non-visual activation state disclosure: the compiled shell supplies
    // canopyWindowActivation from the fail-closed host adapter.
    readonly property bool activationAvailable: canopyWindowActivation
        ? canopyWindowActivation.indicatorsAvailable : false
    readonly property int activationSequence: canopyWindowActivation
        ? canopyWindowActivation.sequence : -1
    readonly property bool windowRunning: activationAvailable
        && activationSequence >= 0
        && canopyWindowActivation.running(iconName)
    readonly property bool windowActive: activationAvailable
        && activationSequence >= 0
        && canopyWindowActivation.active(iconName)
    readonly property string activationIntent: activationAvailable
        && activationSequence >= 0
        ? canopyWindowActivation.activation(iconName, "Canopy") : "REJECT"
    readonly property string activationDescription: {
        if (!activationAvailable)
            return iconName + " window activation state unavailable"
        if (windowActive)
            return iconName + " active window"
        if (windowRunning)
            return iconName + " running; focus requires an explicit grant"
        if (activationIntent === "LAUNCH")
            return iconName + " available to launch"
        if (activationIntent === "IGNORE")
            return iconName + " activation ignored"
        return iconName + " preview only; not installed in this session"
    }
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
    width: 58
    height: 70
    implicitWidth: 58
    implicitHeight: 70
    padding: 0
    hoverEnabled: true
    onClicked: tile.activated(tile.iconName)
    Accessible.name: iconName + " preview"
    Accessible.description: tile.activationDescription
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
