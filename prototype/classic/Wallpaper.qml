import QtQuick

// The exact, owner-approved alpine lake master is bundled as an immutable
// Qt resource. A validated --landscape-wallpaper path can override it.
// Static Qt image decoding only: no polling, effects or background animation.
Item {
    id: wallpaper
    objectName: "canopyWallpaper"
    Accessible.name: "Canopy Classic approved alpine lake wallpaper"

    Rectangle {
        anchors.fill: parent
        color: "#314b5a"
    }
    Image {
        id: alpineLakeMaster
        objectName: "canopyWallpaperImage"
        anchors.fill: parent
        // This image always loads the exact approved master on regular launch.
        // Historical wave remains only in the test-fixture directory.
        source: canopyLandscapeWallpaperUrl.length > 0
                ? canopyLandscapeWallpaperUrl
                : "qrc:/Canopy/Classic/assets/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        cache: true
        smooth: true
        // The native photo is cached at a bounded resolution for HiDPI.
        // No shaders, per-frame blur, pollers, or wallpaper animation.
        sourceSize: Qt.size(Math.min(1920, Math.ceil(wallpaper.width * 2)),
                            Math.min(1080, Math.ceil(wallpaper.height * 2)))
        Accessible.name: "Static desktop wallpaper artwork"
    }
    readonly property bool landscapeActive: canopyLandscapeWallpaperUrl.length > 0
    readonly property bool imageReady: alpineLakeMaster.status === Image.Ready
}
