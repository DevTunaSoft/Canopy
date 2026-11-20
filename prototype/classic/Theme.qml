import QtQuick

// Single instance: shared visual constants without timers, services or effects.
QtObject {
    readonly property color backgroundTop: "#cbdff2"
    readonly property color backgroundBottom: "#eef2f8"
    readonly property color foreground: "#273345"
    readonly property color muted: "#69798b"
    readonly property color accent: "#537da4"
    readonly property color chrome: "#ed1f2326"
    readonly property color dockSurface: "#d91f2326"
    readonly property color dockBorder: "#80f7f5eb"
    readonly property color tile: "#e8eff8"
    readonly property color tileHover: "#d7e7f7"
    readonly property color indicator: "#d8b87a"
    readonly property int barHeight: 32
    readonly property int dockSize: 88
    readonly property int dockPadding: 12
    readonly property int dockSpacing: 7
    readonly property int tileSize: 52
    readonly property int cornerRadius: 24
}
