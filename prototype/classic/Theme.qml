import QtQuick

// Single instance: shared visual constants without timers, services or effects.
QtObject {
    readonly property color backgroundTop: "#cbdff2"
    readonly property color backgroundBottom: "#eef2f8"
    readonly property color foreground: "#273345"
    readonly property color muted: "#69798b"
    readonly property color accent: "#537da4"
    readonly property color chrome: "#edf6f9fc"
    readonly property color dockSurface: "#cce7eef4"
    readonly property color dockBorder: "#ccffffff"
    readonly property color tile: "#e8eff8"
    readonly property color tileHover: "#d7e7f7"
    readonly property color indicator: "#567aab"
    readonly property int barHeight: 40
    readonly property int dockSize: 76
    readonly property int dockPadding: 10
    readonly property int dockSpacing: 10
    readonly property int tileSize: 52
    readonly property int cornerRadius: 21
}
