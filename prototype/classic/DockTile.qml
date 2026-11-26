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
    width: 58
    height: 70
    implicitWidth: 58
    implicitHeight: 70
    padding: 0
    hoverEnabled: true
    activeFocusOnTab: true
    onClicked: tile.activated(tile.iconName)

    // PE-035: the keyboard gate's dock_arrow_next step claims that Right
    // moves focus to the next dock tile. Move real Qt active focus between
    // the Repeater siblings; no geometry, colour or visual state is changed.
    // BEGIN PE-035 PURE FOCUS INDEX LOGIC
    function dockFocusIndex(currentIndex, count, direction, absolute) {
        if (count <= 0) return -1
        if (absolute !== undefined) {
            return Math.max(0, Math.min(count - 1, absolute))
        }
        if (currentIndex < 0) return direction > 0 ? 0 : count - 1
        let target = currentIndex + direction
        if (target < 0) target = count - 1
        else if (target >= count) target = 0
        return target
    }
    // END PE-035 PURE FOCUS INDEX LOGIC
    function dockSiblings() {
        const siblings = []
        const row = tile.parent
        if (!row) return siblings
        const children = row.children
        for (let i = 0; i < children.length; ++i) {
            if (children[i].objectName === "canopyDockTile") siblings.push(children[i])
        }
        return siblings
    }
    function dockMoveFocus(direction, absolute) {
        const tiles = tile.dockSiblings()
        if (tiles.length === 0) return
        const index = tiles.indexOf(tile)
        const target = tile.dockFocusIndex(index, tiles.length, direction, absolute)
        if (target >= 0 && target < tiles.length) tiles[target].forceActiveFocus()
    }
    Keys.onRightPressed: function(event) { event.accepted = true; tile.dockMoveFocus(1) }
    Keys.onLeftPressed: function(event) { event.accepted = true; tile.dockMoveFocus(-1) }
    // Qt Quick Keys has no dedicated Home/End signals: use the generic
    // pressed handler so Home/End are real key events too.
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Home) {
            event.accepted = true
            tile.dockMoveFocus(0, 0)
        } else if (event.key === Qt.Key_End) {
            event.accepted = true
            tile.dockMoveFocus(0, tile.dockSiblings().length - 1)
        }
    }

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
