import QtQuick
import QtQuick.Controls

// A single, wall-clock-aligned wakeup per minute. No animated updates,
// polling loop, extra process, compositor work or background service.
Label {
    id: clock
    objectName: "canopyTopBarClock"
    property date currentTime: new Date()
    readonly property bool refreshScheduled: nextMinute.running

    // The original font, colour and geometry stay frozen; only the date/time
    // separator is explicit so a one-digit day cannot read as a stray glyph.
    text: Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +
          Qt.formatTime(currentTime, "h:mm AP")
    color: "#f7f5eb"
    font.pixelSize: 12
    font.weight: Font.Medium
    Accessible.role: Accessible.StaticText
    Accessible.name: "Local date and time: " + text

    function refreshClock() {
        const now = new Date()
        currentTime = now
        // Wake just after the next local minute boundary, including after
        // sleep/resume; no repetitive per-second or per-frame timer.
        nextMinute.interval = Math.max(1, 60000 -
            (now.getSeconds() * 1000 + now.getMilliseconds()))
        if (visible)
            nextMinute.restart()
    }

    Timer {
        id: nextMinute
        interval: 60000
        repeat: false
        running: false
        onTriggered: clock.refreshClock()
    }

    onVisibleChanged: {
        if (visible)
            refreshClock()
        else
            nextMinute.stop()
    }
    Connections {
        target: Qt.application
        function onStateChanged() {
            if (Qt.application.state === Qt.ApplicationActive)
                clock.refreshClock()
        }
    }
    Component.onCompleted: refreshClock()
}
