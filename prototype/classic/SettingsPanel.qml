import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Classic settings panel. Fail closed by construction: no setting is guessed,
// no privileged host change is performed, no new event topic or daemon is
// created, and none of the approved artwork/geometry is modified. Availability
// and disclosure text come only from trusted host contracts. The single
// persisted preference uses the reduced-motion value domain from
// canopy_features/accessibility/reduced_motion_contract.py; everything else is
// visibly disclosed as unavailable until a real host adapter exists.
FocusScope {
    id: settingsPanel
    objectName: "canopySettingsPanel"

    property bool opened: false
    // Optional trusted host adapter exposing view(key) -> QVariantMap and
    // setPreference(key, value) -> bool. Absent by default: no fake settings.
    property var controller: null
    property string settingsApp: "Settings"
    property string selectionMessage: ""
    readonly property var keys: [
        "reduced_motion", "network", "audio", "power",
        "session", "shell_pack", "notifications", "theme"
    ]
    readonly property int rowCount: keys.length

    signal preferenceChanged(string key, string value)
    signal settingsLaunchFailed(string key)

    // ND-041 state binding only. The compiled shell registers the same
    // read-only preference bridge as `canopySettingsPreferences` and injects it
    // as `controller`. Prefer an explicitly injected controller; fall back to
    // the registered context source only when it satisfies the trusted view
    // shape. No timer, file, socket, process or second preference store.
    function trustedController(candidate) {
        return candidate !== null
                && typeof candidate === "object"
                && typeof candidate.view === "function"
                && typeof candidate.setPreference === "function"
                ? candidate : null
    }

    function preferencesController() {
        var injected = trustedController(controller)
        if (injected)
            return injected
        if (typeof canopySettingsPreferences !== "undefined")
            return trustedController(canopySettingsPreferences)
        return null
    }

    function bridgeReady() {
        return typeof canopySystemLaunchEnabled !== "undefined"
                && canopySystemLaunchEnabled === true
                && typeof canopySystemLauncher !== "undefined"
                && canopySystemLauncher !== null
                && typeof canopySystemLauncher.canLaunch === "function"
                && canopySystemLauncher.canLaunch(settingsApp)
    }

    function titleFor(key) {
        switch (key) {
        case "reduced_motion": return "Reduced motion"
        case "network": return "Network"
        case "audio": return "Sound"
        case "power": return "Power"
        case "session": return "Session"
        case "shell_pack": return "Shell pack"
        case "notifications": return "Notifications"
        case "theme": return "Appearance"
        default: return "Unknown"
        }
    }

    function allowedValues(key) {
        return key === "reduced_motion" ? ["unset", "full", "reduce"] : []
    }

    // Stable fallback used when no trusted model is registered. It describes
    // absence instead of inventing state or writing any durable value.
    function fallbackView(key) {
        var closed = "Unavailable — no persisted preference store"
        return {
            key: key,
            title: titleFor(key),
            value: "",
            available: false,
            disclosure: closed,
            source: "none"
        }
    }

    function viewFor(key) {
        var adapter = preferencesController()
        if (adapter) {
            let supplied = null
            try {
                supplied = adapter.view(key)
            } catch (error) {
                supplied = null
            }
            if (supplied && typeof supplied === "object"
                    && supplied.key === key
                    && typeof supplied.title === "string"
                    && supplied.title.length <= 64
                    && typeof supplied.value === "string"
                    && supplied.value.length <= 16
                    && typeof supplied.available === "boolean"
                    && typeof supplied.disclosure === "string"
                    && supplied.disclosure.length <= 128
                    && typeof supplied.source === "string"
                    && supplied.source.length <= 64
                    && /^[\x20-\x7e]*$/.test(supplied.source)) {
                const allowed = allowedValues(key)
                // Unavailable rows must carry no value at all; a stored value
                // is accepted only for the one contract-backed key.
                const valueFits = allowed.length === 0
                        ? supplied.value === ""
                        : (supplied.available
                           && allowed.indexOf(supplied.value) >= 0)
                if (valueFits)
                    return supplied
            }
        }
        return fallbackView(key)
    }

    function canSet(key, value) {
        var allowed = allowedValues(key)
        var view = viewFor(key)
        return allowed.length > 0 && allowed.indexOf(value) >= 0
                && view.available === true
                && preferencesController() !== null
                && typeof preferencesController().setPreference === "function"
    }

    function setValue(key, value) {
        if (!canSet(key, value)) {
            selectionMessage = titleFor(key) + " — " + viewFor(key).disclosure
            return false
        }
        var accepted = preferencesController().setPreference(key, value)
        if (accepted === true) {
            selectionMessage = "Saved " + titleFor(key).toLowerCase()
                    + "; approved preview visuals do not change"
            preferenceChanged(key, value)
        } else {
            selectionMessage = titleFor(key)
                    + " — Unavailable — could not persist preference"
        }
        return accepted === true
    }

    function openSystemSettings() {
        if (!bridgeReady()) {
            selectionMessage = "System Settings — "
                    + "Unavailable — host control bridge disabled"
            settingsLaunchFailed("system_settings")
            return
        }
        // Existing opt-in host bridge only: no process API or shell command.
        if (canopySystemLauncher.launch(settingsApp))
            selectionMessage = "Opened system Settings through the host bridge"
        else {
            selectionMessage = "Settings bridge could not open system Settings"
            settingsLaunchFailed("system_settings")
        }
    }

    function openPanel() {
        opened = true
        selectionMessage = ""
        settingsPanel.forceActiveFocus()
    }
    function closePanel() {
        opened = false
        selectionMessage = ""
    }
    function togglePanel() {
        if (opened) closePanel()
        else openPanel()
    }

    visible: opened
    focus: opened
    Keys.onEscapePressed: settingsPanel.closePanel()

    Rectangle {
        anchors.fill: parent
        color: "#690d1a2b"
        MouseArea {
            anchors.fill: parent
            onClicked: settingsPanel.closePanel()
        }
    }

    Rectangle {
        id: panel
        objectName: "canopySettingsPanelCard"
        anchors.centerIn: parent
        width: Math.min(parent.width - 42, 540)
        height: Math.min(parent.height - 50, 468)
        radius: 22
        color: "#f3f8fc"
        border.width: 1
        border.color: "#b7d0dce8"
        clip: true

        Label {
            id: heading
            anchors.top: parent.top
            anchors.topMargin: 14
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Settings"
            color: "#2b3e52"
            font.pixelSize: 19
            font.weight: Font.DemiBold
            Accessible.name: "Settings"
        }
        Label {
            id: subheading
            anchors.top: heading.bottom
            anchors.topMargin: 3
            anchors.horizontalCenter: parent.horizontalCenter
            width: panel.width - 36
            text: "Preferences are saved locally; unavailable settings stay disabled"
            color: "#69798b"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            Accessible.name: text
            Accessible.description: "Only contract-backed preferences can be saved"
        }

        Flickable {
            id: rowsViewport
            anchors.top: subheading.bottom
            anchors.topMargin: 10
            anchors.left: panel.left
            anchors.right: panel.right
            anchors.bottom: message.top
            anchors.bottomMargin: 6
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            contentWidth: width
            contentHeight: rowsColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: rowsColumn
                width: rowsViewport.width
                spacing: 4

                Repeater {
                    model: settingsPanel.keys
                    delegate: Rectangle {
                        id: settingRow
                        required property string modelData
                        objectName: "canopySettingsRow"
                        width: rowsColumn.width
                        height: 40
                        radius: 12
                        color: "#ffffff"
                        border.width: 1
                        border.color: "#d5e1ec"
                        Accessible.name: settingsPanel.titleFor(modelData)
                                + " setting"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            anchors.topMargin: 4
                            anchors.bottomMargin: 4
                            spacing: 8

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Label {
                                    objectName: "canopySettingsTitle"
                                    Layout.fillWidth: true
                                    text: settingsPanel.viewFor(modelData).title
                                    color: "#273345"
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Accessible.name: text
                                }
                                Label {
                                    id: disclosureLabel
                                    objectName: "canopySettingsDisclosure"
                                    Layout.fillWidth: true
                                    text: settingsPanel.viewFor(modelData).disclosure
                                    color: "#69798b"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                    Accessible.name: text
                                }
                            }

                            Repeater {
                                id: optionButtons
                                model: settingsPanel.allowedValues(modelData)
                                delegate: Button {
                                    id: optionButton
                                    required property string modelData
                                    objectName: "canopySettingsOptionButton"
                                    Layout.preferredHeight: 24
                                    checkable: true
                                    text: {
                                        switch (modelData) {
                                        case "unset": return "Default"
                                        case "full": return "Full"
                                        case "reduce": return "Reduce"
                                        default: return modelData
                                        }
                                    }
                                    enabled: settingsPanel.canSet(settingRow.modelData,
                                                                  modelData)
                                    checked: enabled && settingsPanel.viewFor(
                                                   settingRow.modelData).value === modelData
                                    hoverEnabled: true
                                    Accessible.name: text + " reduced motion"
                                    Accessible.description: disclosureLabel.text
                                    onClicked: settingsPanel.setValue(
                                                   settingRow.modelData, modelData)
                                    background: Rectangle {
                                        radius: 8
                                        color: optionButton.enabled
                                               && (optionButton.hovered
                                                   || optionButton.checked)
                                               ? "#d7e7f7" : "#eef2f8"
                                        border.width: 1
                                        border.color: "#b7d0dce8"
                                    }
                                    contentItem: Label {
                                        text: optionButton.text
                                        color: optionButton.enabled
                                               ? "#273345" : "#69798b"
                                        font.pixelSize: 10
                                        verticalAlignment: Text.AlignVCenter
                                        horizontalAlignment: Text.AlignHCenter
                                        Accessible.name: text
                                    }
                                }
                            }

                            Button {
                                id: unavailableButton
                                objectName: "canopySettingsUnavailableButton"
                                visible: optionButtons.count === 0
                                Layout.preferredHeight: 24
                                text: "Unavailable"
                                enabled: false
                                Accessible.name: settingsPanel.titleFor(modelData)
                                        + " unavailable"
                                Accessible.description: disclosureLabel.text
                                background: Rectangle {
                                    radius: 8
                                    color: "#eef2f8"
                                    border.width: 1
                                    border.color: "#b7d0dce8"
                                }
                                contentItem: Label {
                                    text: unavailableButton.text
                                    color: "#69798b"
                                    font.pixelSize: 10
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
            objectName: "canopySettingsMessage"
            anchors.left: panel.left
            anchors.right: panel.right
            anchors.bottom: systemButton.top
            anchors.bottomMargin: 4
            anchors.leftMargin: 20
            anchors.rightMargin: 20
            text: settingsPanel.selectionMessage
            color: "#31475e"
            font.pixelSize: 10
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

        Button {
            id: systemButton
            objectName: "canopySettingsOpenSystem"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 12
            Layout.preferredHeight: 26
            text: "Open system Settings"
            enabled: settingsPanel.bridgeReady()
            hoverEnabled: true
            Accessible.name: text
            Accessible.description: enabled
                    ? "Opens the system Settings app through the host bridge"
                    : "Unavailable — host control bridge disabled"
            onClicked: settingsPanel.openSystemSettings()
            background: Rectangle {
                radius: 8
                color: systemButton.enabled
                       && (systemButton.hovered || systemButton.activeFocus)
                       ? "#d7e7f7" : "#eef2f8"
                border.width: 1
                border.color: "#b7d0dce8"
            }
            contentItem: Label {
                text: systemButton.text
                color: systemButton.enabled ? "#273345" : "#69798b"
                font.pixelSize: 11
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                Accessible.name: text
            }
        }
    }
}
