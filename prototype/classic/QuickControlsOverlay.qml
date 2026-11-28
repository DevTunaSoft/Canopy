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
    // Optional read-only host-state controller from
    // canopy_features/quick_controls/host_state.py. It uses the same view()
    // contract and adds bounded detail_kind/detail_value fields for real
    // volume and brightness observations. Absent by default: fail closed.
    property var hostState: null
    // Optional trusted host adapter exposing request(domain, action) -> bool.
    // Absent by default: direct controls must not pretend to work.
    property var actionBridge: null
    property string settingsApp: "Settings"
    property string selectionMessage: ""
    readonly property var domains: ["network", "audio", "power", "session"]
    readonly property int domainCount: domains.length

    signal controlRequested(string domain, string action)
    signal settingsLaunchFailed(string domain)

    // ND-041 state binding only. The compiled shell registers the read-only
    // host controller as `canopyHostState` and injects the same object as
    // `hostState`. Prefer the explicit injection, then the registered context
    // source, then the older fail-closed controller. Every candidate must pass
    // the same bounded view gate below; no timer, socket, file, process or
    // second status service is introduced.
    function trustedAdapter(candidate) {
        return candidate !== null
                && typeof candidate === "object"
                && typeof candidate.view === "function"
                ? candidate : null
    }

    function labelForStatus(status) {
        switch (status) {
        case "connected": return "Connected"
        case "disconnected": return "Not connected"
        case "muted": return "Muted"
        case "unmuted": return "Sound on"
        case "charging": return "Charging"
        case "discharging": return "On battery"
        case "active": return "Active"
        case "locked": return "Locked"
        case "suspended": return "Suspended"
        default: return "Unknown — no host status"
        }
    }

    function knownStatus(domain, status) {
        if (typeof status !== "string")
            return false
        if (status === "unknown")
            return true
        if (labelForStatus(status) === "Unknown — no host status")
            return false
        switch (domain) {
        case "network":
            return status === "connected" || status === "disconnected"
        case "audio":
            return status === "muted" || status === "unmuted"
        case "power":
            return status === "charging" || status === "discharging"
        case "session":
            return status === "active" || status === "locked"
                    || status === "suspended"
        default:
            return false
        }
    }

    function disclosureForReason(reason) {
        switch (reason) {
        case "ok": return "Available"
        case "no-host-observation":
            return "Unavailable — no host status observation"
        case "no-host-interface":
            return "Unavailable — no host control interface"
        case "bridge-disabled":
            return "Unavailable — host control bridge disabled"
        case "privileged-host-change":
            return "Unavailable — privileged host changes are not performed"
        case "invalid-domain":
            return "Unavailable — unknown control domain"
        case "invalid-action":
            return "Unavailable — unknown control action"
        case "invalid-grant":
            return "Unavailable — invalid capability grant"
        default: return ""
        }
    }

    function trustedDecision(decision) {
        return !!decision && typeof decision === "object"
                && typeof decision.allowed === "boolean"
                && typeof decision.reason === "string"
                && typeof decision.disclosure === "string"
                && decision.allowed === (decision.reason === "ok")
                && disclosureForReason(decision.reason) === decision.disclosure
    }

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

    // Accept only bounded, enumerated host observations. A broken adapter can
    // never inject unbounded text, an unenumerated status/decision or an
    // untrusted provenance into the UI. Every fixed label/disclosure mirrors
    // canopy_features/system/quick_controls_state.py.
    function trustedView(domain, adapter) {
        if (!trustedAdapter(adapter))
            return null
        var supplied
        try {
            supplied = adapter.view(domain)
        } catch (error) {
            return null
        }
        if (!supplied || typeof supplied !== "object"
                || supplied.domain !== domain
                || !knownStatus(domain, supplied.status)
                || typeof supplied.status_label !== "string"
                || supplied.status_label.length > 64
                || supplied.status_label !== labelForStatus(supplied.status)
                || typeof supplied.source !== "string"
                || supplied.source.length > 64
                || !/^[a-z0-9_.:-]*$/.test(supplied.source)
                || typeof supplied.observed !== "boolean"
                || (supplied.availability !== "AVAILABLE"
                    && supplied.availability !== "UNAVAILABLE")
                || !trustedDecision(supplied.control)
                || !trustedDecision(supplied.settings))
            return null
        var kind = supplied.detail_kind
        if (kind !== undefined && kind !== "" && kind !== "volume"
                && kind !== "brightness")
            return null
        var value = supplied.detail_value
        if (kind === "volume" || kind === "brightness") {
            if (typeof value !== "number" || value < 0 || value > 100
                    || Math.floor(value) !== value)
                return null
        }
        return supplied
    }

    function viewFor(domain) {
        var supplied = trustedView(domain, hostState)
        if (!supplied && typeof canopyHostState !== "undefined")
            supplied = trustedView(domain, canopyHostState)
        if (!supplied)
            supplied = trustedView(domain, controller)
        if (supplied)
            return supplied
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
        var label = view.status_label || "Unknown — no host status"
        if (typeof label !== "string" || label.length > 64)
            label = "Unknown — no host status"
        var kind = view.detail_kind
        var value = view.detail_value
        if ((kind === "volume" || kind === "brightness")
                && typeof value === "number" && value >= 0 && value <= 100
                && Math.floor(value) === value) {
            const prefix = kind === "volume" ? " · Volume " : " · Brightness "
            return label + prefix + value + "%"
        }
        return label
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
            Accessible.name: text
            Accessible.description: "Host-reported status; unavailable controls stay disabled"
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
                                Accessible.name: text
                            }
                            Item { Layout.fillWidth: true }
                            Label {
                                objectName: "canopyQuickStatus"
                                text: quickControls.statusFor(modelData)
                                color: "#537da4"
                                font.pixelSize: 12
                                Accessible.name: text
                                Accessible.description: quickControls.titleFor(modelData) + " host status"
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
                                    Accessible.name: text
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
                                    Accessible.name: text
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
            Accessible.role: Accessible.AlertMessage
            Accessible.ignored: message.text === ""
            // A11Y-ANNOUNCE-BEGIN
            property bool a11yAnnounceReady: false
            Component.onCompleted: a11yAnnounceReady = true
            onTextChanged: {
                if (text === "" || !a11yAnnounceReady)
                    return;
                if (canopyStatusAnnouncer.nativeAnnounceAvailable)
                    Accessible.announce(text, Accessible.Assertive);
                else
                    canopyStatusAnnouncer.announce(message, text);
            }
            // A11Y-ANNOUNCE-END
        }
    }
}
