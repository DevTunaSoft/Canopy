import QtQuick
import QtQuick.Controls

// A single, wall-clock-aligned wakeup per minute. No animated updates,
// polling loop, extra process, compositor work or background service.
Label {
    id: clock
    objectName: "canopyTopBarClock"
    property date currentTime: new Date()
    readonly property bool refreshScheduled: nextMinute.running

    // An explicit separator keeps a one-digit day legible next to the time.
    // Font size, weight, geometry and the single minute-wakeup timer are
    // unchanged. Screen readers receive the unabbreviated local date instead
    // of the compact visible spelling ("Tue"/"Nov").
    text: Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +
          Qt.formatTime(currentTime, "h:mm AP")
    readonly property string spokenDateTime: Qt.formatDate(currentTime, "dddd, d MMMM") +
                                             ", " + Qt.formatTime(currentTime, "h:mm AP")

    // Approved mode paints a translucent light plate over the wave wallpaper:
    // dark ink holds AA contrast there. The default dark chrome keeps the
    // original off-white (color: "#f7f5eb").
    color: canopyApprovedMode ? "#1f2326" : "#f7f5eb"
    font.pixelSize: 12
    font.weight: Font.Medium
    Accessible.role: Accessible.StaticText
    Accessible.name: "Local date and time: " + spokenDateTime

    // Delay is derived from the wall clock, never from a free-running counter.
    // A 1 ms floor keeps a wakeup at an exact boundary from firing twice.
    function nextMinuteDelay(now) {
        return Math.max(1, 60000 -
            (now.getSeconds() * 1000 + now.getMilliseconds()))
    }

    function refreshClock() {
        const now = new Date()
        currentTime = now
        // Wake just after the next local minute boundary, including after
        // sleep/resume; no repetitive per-second or per-frame timer.
        nextMinute.interval = nextMinuteDelay(now)
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
