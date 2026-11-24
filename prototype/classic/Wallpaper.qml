import QtQuick

// Static authored vector art, converted to pixels by the Qt SVG image plugin.
// The shared asset is source-controlled, requires no network or background work,
// and is drawn once per resolution/theme change rather than in an animation loop.
Item {
    id: wallpaper
    objectName: "canopyWallpaper"
    Accessible.name: "Canopy Classic approved alpine lake master wallpaper"

    Rectangle {
        anchors.fill: parent
        color: "#92c7d9"
    }
    Image {
        id: blueCurrent
        objectName: "canopyWallpaperImage"
        anchors.fill: parent
        // Always use the exact 1920x1080 user-approved alpine master by
        // default, including a regular launch with no special arguments.
        // A separately validated --landscape-wallpaper remains an override.
        source: canopyLandscapeWallpaperUrl.length > 0
                ? canopyLandscapeWallpaperUrl
                : "qrc:/Canopy/Classic/assets/wallpapers/Canopy_Classic_Master_Wallpaper_1920x1080.png"
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        cache: true
        smooth: true
        // The native photo is cached at a bounded resolution for HiDPI.
        // No shaders, per-frame blur, pollers, or wallpaper animation.
        sourceSize: canopyLandscapeWallpaperUrl.length > 0
                    ? Qt.size(Math.min(3840, Math.ceil(wallpaper.width * 2)),
                              Math.min(2160, Math.ceil(wallpaper.height * 2)))
                    : Qt.size(1920, 1080)
        Accessible.name: "Static desktop wallpaper artwork"
    }
    readonly property bool landscapeActive: canopyLandscapeWallpaperUrl.length > 0
    readonly property bool imageReady: blueCurrent.status === Image.Ready
}
