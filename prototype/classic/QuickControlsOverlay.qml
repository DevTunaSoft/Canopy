import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Classic quick controls. Fail closed by construction: no status is guessed,
// no hardware is probed, no service/socket/process is created, and no
// privileged host change is performed. Status and grants come only from a
// trusted host adapter; missing adapters leave every control visibly
// unavailable. The only action Classic can actually take today is opening the
// existing system Settings app through the host-owned GIO launch bridge.
FocusScope {
    id: quickControls
    objectName: "canopyQuickControlsOverlay"

    property bool opened: false
    // Optional trusted host adapter exposing view(domain) -> QVariantMap.
    // The Python contract lives in canopy_features/system/quick_controls_state.py.
    property var controller: null
    // Optional trusted host adapter exposing request(domain, action) -> bool.
    // Absent by default: direct controls must not pretend to work.
    property var actionBridge: null
    property string settingsApp: "Settings"
    property string selectionMessage: ""
    readonly property var domains: ["network", "audio", "power", "session"]
    readonly property int domainCount: domains.length

    signal controlRequested(string domain, string action)
    signal settingsLaunchFailed(string domain)

    function defaultControlDisclosure(domain) {
        if (domain === "power" || domain === "session")
            return "Unavailable — privileged host changes are not performed"
        return "Unavailable — no host control interface"
    }

    function bridgeReady() {
        return typeof canopySystemLaunchEnabled !== "undefined"
                && canopySystemLaunchEnabled === true
                && typeof canopySystemLauncher !== "undefined"
                && canopySystemLauncher !== null
                && typeof canopySystemLauncher.canLaunch === "function"
                && canopySystemLauncher.canLaunch(settingsApp)
    }

    // Stable fallback used when no trusted model is registered. It describes
    // absence instead of inventing state.
    function fallbackView(domain) {
        var ready = bridgeReady()
        return {
            domain: domain,
            status: "unknown",
            status_label: "Unknown — no host status",
            source: "none",
            observed: false,
            availability: ready ? "AVAILABLE" : "UNAVAILABLE",
            control: {
                allowed: false,
                reason: "no-host-interface",
                disclosure: defaultControlDisclosure(domain)
            },
            settings: {
                allowed: ready,
                reason: ready ? "ok" : "bridge-disabled",
                disclosure: ready ? "Available"
                                  : "Unavailable — host control bridge disabled"
            }
        }
    }

    function viewFor(domain) {
        if (controller && typeof controller.view === "function") {
            const supplied = controller.view(domain)
            if (supplied && typeof supplied === "object"
                    && typeof supplied.control === "object"
                    && typeof supplied.settings === "object")
                return supplied
        }
        return fallbackView(domain)
    }

    function titleFor(domain) {
        switch (domain) {
        case "network": return "Network"
        case "audio": return "Sound"
        case "power": return "Power"
        case "session": return "Session"
        default: return "Unknown"
        }
    }

    function actionFor(domain) {
        switch (domain) {
        case "network": return "toggle_wifi"
        case "audio": return "toggle_mute"
        case "power": return "suspend"
        case "session": return "lock"
        default: return ""
        }
    }

    function statusFor(domain) {
        var view = viewFor(domain)
        return view.status_label || "Unknown — no host status"
    }

    function disclosureFor(domain) {
        var view = viewFor(domain)
        return view.control && view.control.disclosure
                ? view.control.disclosure
                : "Unavailable — no host control interface"
    }

    function canControl(domain) {
        var view = viewFor(domain)
        return !!(view.control && view.control.allowed
                  && actionBridge && typeof actionBridge.request === "function")
    }

    function canOpenSettings(domain) {
        var view = viewFor(domain)
        return !!(view.settings && view.settings.allowed && bridgeReady())
    }

    function openSettings(domain) {
        if (!canOpenSettings(domain)) {
            selectionMessage = titleFor(domain) + " settings "
                    + viewFor(domain).settings.disclosure
            settingsLaunchFailed(domain)
            return
        }
        // Existing host bridge only. No process API, shell command or privilege.
        if (canopySystemLauncher.launch(settingsApp)) {
            selectionMessage = "Opened system Settings for "
                    + titleFor(domain).toLowerCase()
        } else {
            selectionMessage = "Settings bridge could not open "
                    + titleFor(domain).toLowerCase()
            settingsLaunchFailed(domain)
        }
    }

    function requestControl(domain) {
        if (!canControl(domain)) {
            selectionMessage = titleFor(domain) + " " + disclosureFor(domain)
            return
        }
        var action = actionFor(domain)
        var accepted = actionBridge.request(domain, action)
        controlRequested(domain, action)
        selectionMessage = accepted
                ? titleFor(domain) + " request accepted by host"
                : titleFor(domain) + " request refused by host"
    }

    function openControls() {
        opened = true
        selectionMessage = ""
        quickControls.forceActiveFocus()
    }
    function closeControls() {
        opened = false
        selectionMessage = ""
    }
    function toggleControls() {
        if (opened) closeControls()
        else openControls()
    }

    visible: opened
    focus: opened
    Keys.onEscapePressed: quickControls.closeControls()

    Rectangle {
        anchors.fill: parent
        color: "#690d1a2b"
        MouseArea {
            anchors.fill: parent
            onClicked: quickControls.closeControls()
        }
    }

    Rectangle {
        id: panel
        objectName: "canopyQuickControlsPanel"
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
            anchors.top: parent.top
            anchors.topMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Quick controls"
            color: "#2b3e52"
            font.pixelSize: 19
            font.weight: Font.DemiBold
            Accessible.name: "Quick controls"
        }
        Label {
            id: subheading
            anchors.top: heading.bottom
            anchors.topMargin: 4
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Status comes from the host; unavailable controls stay disabled"
            color: "#69798b"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            width: panel.width - 40
        }

        Column {
            id: rows
            anchors.top: subheading.bottom
            anchors.topMargin: 14
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            spacing: 8

            Repeater {
                model: quickControls.domains
                delegate: Rectangle {
                    id: controlRow
                    required property string modelData
                    objectName: "canopyQuickControlRow"
                    width: rows.width
                    height: 82
                    radius: 14
                    color: "#ffffff"
                    border.width: 1
                    border.color: "#d5e1ec"
                    Accessible.name: quickControls.titleFor(modelData)
                            + " quick control"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 3
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: quickControls.titleFor(modelData)
                                color: "#273345"
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            Item { Layout.fillWidth: true }
                            Label {
                                objectName: "canopyQuickStatus"
                                text: quickControls.statusFor(modelData)
                                color: "#537da4"
                                font.pixelSize: 12
                            }
                        }
                        Label {
                            objectName: "canopyQuickDisclosure"
                            Layout.fillWidth: true
                            text: quickControls.disclosureFor(modelData)
                            color: "#69798b"
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                            Accessible.name: text
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Button {
                                id: settingsButton
                                objectName: "canopyQuickSettingsButton"
                                Layout.preferredHeight: 24
                                text: "Open Settings"
                                enabled: quickControls.canOpenSettings(modelData)
                                hoverEnabled: true
                                Accessible.name: "Open "
                                        + quickControls.titleFor(modelData)
                                        + " settings"
                                onClicked: quickControls.openSettings(modelData)
                                background: Rectangle {
                                    radius: 8
                                    color: settingsButton.enabled
                                           && (settingsButton.hovered
                                               || settingsButton.activeFocus)
                                           ? "#d7e7f7" : "#eef2f8"
                                    border.width: 1
                                    border.color: "#b7d0dce8"
                                }
                                contentItem: Label {
                                    text: settingsButton.text
                                    color: settingsButton.enabled
                                           ? "#273345" : "#69798b"
                                    font.pixelSize: 11
                                    verticalAlignment: Text.AlignVCenter
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                            Button {
                                id: controlButton
                                objectName: "canopyQuickControlButton"
                                Layout.preferredHeight: 24
                                text: quickControls.titleFor(modelData)
                                      + " control"
                                enabled: quickControls.canControl(modelData)
                                hoverEnabled: true
                                Accessible.name: text
                                Accessible.description: quickControls.disclosureFor(modelData)
                                onClicked: quickControls.requestControl(modelData)
                                background: Rectangle {
                                    radius: 8
                                    color: controlButton.enabled
                                           && (controlButton.hovered
                                               || controlButton.activeFocus)
                                           ? "#d7e7f7" : "#eef2f8"
                                    border.width: 1
                                    border.color: "#b7d0dce8"
                                }
                                contentItem: Label {
                                    text: controlButton.text
                                    color: controlButton.enabled
                                           ? "#273345" : "#69798b"
                                    font.pixelSize: 11
                                    verticalAlignment: Text.AlignVCenter
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                    }
                }
            }
        }

        Label {
            id: message
            objectName: "canopyQuickControlsMessage"
            anchors.left: panel.left
            anchors.right: panel.right
            anchors.bottom: panel.bottom
            anchors.bottomMargin: 14
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            text: quickControls.selectionMessage
            color: "#31475e"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            Accessible.name: text
        }
    }
}
