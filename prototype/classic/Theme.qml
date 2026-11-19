import QtQuick

// Single instance: shared visual constants without timers, services or effects.
QtObject {
    readonly property color backgroundTop: "#17283b"
    readonly property color backgroundBottom: "#09111d"
    readonly property color foreground: "#f6f8fc"
    readonly property color muted: "#aebfd1"
    readonly property color accent: "#a7d5ff"
    readonly property color chrome: "#d91c2a3c"
    readonly property color dockSurface: "#e8243449"
    readonly property color dockBorder: "#637b94"
    readonly property color tile: "#2c425a"
    readonly property color tileHover: "#405d7b"
    readonly property color indicator: "#e9f5ff"
    readonly property int barHeight: 44
    readonly property int dockSize: 72
    readonly property int dockPadding: 10
    readonly property int dockSpacing: 10
    readonly property int tileSize: 52
    readonly property int cornerRadius: 19
}
