import QtQuick
import QtQuick.Controls

// One launcher item, reusing DockTile's exact icon resolution and source map.
// The label and placement are distinct from dock behavior; app launching is
// deliberately not faked and has no background process or polling loop.
Item {
    id: tile
    objectName: "canopyLauncherTile"
    required property string iconName
    signal activated(string name)
    width: 142
    height: 108

    DockTile {
        id: icon
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        iconName: tile.iconName
        artworkPixels: 62
        previewActive: false
        onClicked: tile.activated(tile.iconName)
    }
    Label {
        anchors.top: icon.bottom
        anchors.topMargin: 2
        width: parent.width
        text: tile.iconName
        color: "#fcfdff"
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        font.pixelSize: 12
        font.weight: Font.Medium
    }
}
