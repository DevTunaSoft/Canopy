import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Classic notification centre. Fail closed by construction: no notification
// daemon, no D-Bus/notification-daemon call, no socket, no process, no OS
// polling and no invented rows. The only accepted input is an explicit,
// trusted host source that reports itself connected and supplies bounded
// records tied to an ALREADY DEFINED canopy_core.host_events topic. The
// preview host source is disconnected, so the panel always opens to a visible
// disclosure and zero rows. Opening, refreshing and closing are real local
// actions; no row claims an action Classic cannot perform.
FocusScope {
    id: notificationCenter
    objectName: "canopyNotificationCenterOverlay"

    property bool opened: false
    // Optional trusted host adapter: connected(), source(), allowedTopics()
    // and snapshot() -> array of bounded records. Absent/disconnected by
    // default. Records are never generated inside QML.
    property var controller: null

    // Exact canopy_core.host_events v2 topic contract. No new topic is
    // invented, and no event is emitted from this component.
    readonly property var contractTopics: [
        "app.catalog.changed",
        "window.state.changed",
        "session.state.changed",
        "capabilities.report"
    ]
    readonly property string hostEventSource: "host-events"
    readonly property int maxItems: 12
    readonly property string noSourceDisclosure:
        "Unavailable — no host notification source"
    readonly property string invalidSourceDisclosure:
        "Unavailable — invalid host notification source"

    property var records: []
    property string reason: "no-host-notification-source"
    readonly property int itemCount: records.length
    readonly property bool sourceConnected: reason === "ok"
    readonly property bool controllerPresent:
        controller !== null && typeof controller.snapshot === "function"

    signal notificationSelected(string identifier)

    function connectedFromController() {
        if (!controllerPresent)
            return false
        try {
            if (typeof controller.connected === "function")
                return controller.connected() === true
            if (typeof controller.connected === "boolean")
                return controller.connected === true
        } catch (error) {
            return false
        }
        return false
    }

    function contractMatchesController() {
        if (typeof controller.allowedTopics !== "function")
            return false
        var allowed
        try {
            allowed = controller.allowedTopics()
        } catch (error) {
            return false
        }
        if (!Array.isArray(allowed) || allowed.length !== contractTopics.length)
            return false
        for (var i = 0; i < allowed.length; ++i) {
            if (typeof allowed[i] !== "string"
                    || contractTopics.indexOf(allowed[i]) < 0)
                return false
        }
        return true
    }

    function validRecord(record) {
        if (!record || typeof record !== "object")
            return false
        if (typeof record.id !== "string" || record.id.length < 1
                || record.id.length > 64)
            return false
        if (typeof record.topic !== "string"
                || contractTopics.indexOf(record.topic) < 0)
            return false
        if (record.source !== hostEventSource)
            return false
        if (typeof record.title !== "string" || record.title.length > 120
                || typeof record.body !== "string" || record.body.length > 280)
            return false
        // Refuse control characters before any text reaches a label.
        var text = record.id + record.title + record.body + record.topic
        for (var i = 0; i < text.length; ++i) {
            var code = text.charCodeAt(i)
            if (code < 32 || code === 127)
                return false
        }
        return true
    }

    // One bounded read; never called on a timer. Any malformed record rejects
    // the whole snapshot instead of showing a partial, plausible-looking list.
    function reload() {
        if (!connectedFromController() || !contractMatchesController()) {
            records = []
            reason = "no-host-notification-source"
            return false
        }
        var supplied
        try {
            supplied = controller.snapshot()
        } catch (error) {
            supplied = null
        }
        if (!Array.isArray(supplied) || supplied.length > maxItems) {
            records = []
            reason = "invalid-host-notification-source"
            return false
        }
        var accepted = []
        for (var i = 0; i < supplied.length; ++i) {
            var record = supplied[i]
            if (!validRecord(record)) {
                records = []
                reason = "invalid-host-notification-source"
                return false
            }
            accepted.push({
                id: record.id,
                title: record.title,
                body: record.body,
                source: record.source,
                topic: record.topic
            })
        }
        records = accepted
        reason = "ok"
        return true
    }

    function emptyMessage() {
        if (reason === "no-host-notification-source")
            return noSourceDisclosure
        if (reason === "invalid-host-notification-source")
            return invalidSourceDisclosure
        if (records.length === 0)
            return "No notifications reported by the host"
        return ""
    }

    function openCenter() {
        opened = true
        reload()
        notificationCenter.forceActiveFocus()
    }
    function closeCenter() {
        opened = false
    }
    function toggleCenter() {
        if (opened)
            closeCenter()
        else
            openCenter()
    }

    visible: opened
    focus: opened
    Keys.onEscapePressed: notificationCenter.closeCenter()

    Rectangle {
        anchors.fill: parent
        color: "#690d1a2b"
        MouseArea {
            anchors.fill: parent
            onClicked: notificationCenter.closeCenter()
        }
    }

    Rectangle {
        id: panel
        objectName: "canopyNotificationCenterPanel"
        anchors.centerIn: parent
        width: Math.min(parent.width - 42, 520)
        height: Math.min(parent.height - 72, 462)
        radius: 22
        color: "#f3f8fc"
        border.width: 1
        border.color: "#b7d0dce8"
        clip: true

        Label {
            id: heading
            objectName: "canopyNotificationCenterHeading"
            anchors.top: parent.top
            anchors.topMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Notifications"
            color: "#2b3e52"
            font.pixelSize: 19
            font.weight: Font.DemiBold
            Accessible.name: "Notifications"
        }
        Label {
            id: subheading
            anchors.top: heading.bottom
            anchors.topMargin: 4
            anchors.horizontalCenter: parent.horizontalCenter
            width: panel.width - 40
            text: notificationCenter.emptyMessage() !== ""
                  ? notificationCenter.emptyMessage()
                  : "Host-reported events only; no local notification generation"
            color: "#69798b"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            Accessible.name: text
        }
        Label {
            id: disclosure
            objectName: "canopyNotificationDisclosure"
            anchors.top: subheading.bottom
            anchors.topMargin: 8
            anchors.horizontalCenter: parent.horizontalCenter
            width: panel.width - 40
            text: notificationCenter.emptyMessage()
            visible: text !== ""
            color: "#8a4a32"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            Accessible.name: text
        }

        Rectangle {
            id: emptyState
            objectName: "canopyNotificationEmptyState"
            anchors.top: disclosure.bottom
            anchors.topMargin: 12
            anchors.horizontalCenter: parent.horizontalCenter
            width: panel.width - 40
            height: 210
            radius: 14
            color: "#e6eef5"
            border.width: 1
            border.color: "#cbdbe8"
            visible: notificationCenter.itemCount === 0
            Label {
                anchors.centerIn: parent
                width: parent.width - 28
                text: notificationCenter.reason === "ok"
                      ? "No notifications reported by the host"
                      : "No host notification source — nothing is shown"
                color: "#546b80"
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Accessible.name: text
            }
        }

        Column {
            id: rows
            anchors.top: disclosure.bottom
            anchors.topMargin: 12
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            spacing: 8
            visible: notificationCenter.itemCount > 0

            Repeater {
                model: notificationCenter.records
                delegate: Rectangle {
                    id: notificationRow
                    objectName: "canopyNotificationRow"
                    required property var modelData
                    width: rows.width
                    height: 52
                    radius: 12
                    color: "#ffffff"
                    border.width: 1
                    border.color: "#d6e4ee"
                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Label {
                            width: parent.width
                            text: notificationRow.modelData.title
                            color: "#2b3e52"
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                            Accessible.name: text
                        }
                        Label {
                            width: parent.width
                            text: notificationRow.modelData.body
                            color: "#69798b"
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            Accessible.name: text
                        }
                    }
                }
            }
        }

        RowLayout {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 16
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 12
            Button {
                id: refreshButton
                objectName: "canopyNotificationRefreshButton"
                text: "Refresh"
                enabled: notificationCenter.sourceConnected
                Accessible.name: "Refresh notifications"
                Accessible.description: enabled ? "Read the trusted host source once"
                                               : notificationCenter.noSourceDisclosure
                onClicked: notificationCenter.reload()
            }
            Button {
                id: closeButton
                objectName: "canopyNotificationCloseButton"
                text: "Close"
                Accessible.name: "Close notification centre"
                onClicked: notificationCenter.closeCenter()
            }
        }
    }
}
