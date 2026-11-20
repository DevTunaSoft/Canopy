import QtQuick

// Static authored vector art, converted to pixels by the Qt SVG image plugin.
// The shared asset is source-controlled, requires no network or background work,
// and is drawn once per resolution/theme change rather than in an animation loop.
Item {
    id: wallpaper
    objectName: "canopyWallpaper"
    Accessible.name: "Canopy Blue Current, original flowing blue abstract wallpaper"

    Rectangle {
        anchors.fill: parent
        color: "#92c7d9"
    }
    Image {
        id: blueCurrent
        objectName: "canopyWallpaperImage"
        anchors.fill: parent
        // The accepted concept uses this exact blue wave source PNG.
        // Strict mode refuses missing/mismatched bytes before QML is loaded.
        source: canopyApprovedMode ? canopyApprovedWallpaperUrl
               : "qrc:/Canopy/Classic/assets/wallpapers/blue-current.svg"
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        cache: true
        smooth: true
        sourceSize: Qt.size(1920, 1080)
        Accessible.name: "Static Blue Current wallpaper artwork"
    }
    readonly property bool imageReady: blueCurrent.status === Image.Ready
}
