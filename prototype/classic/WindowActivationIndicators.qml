// Non-visual host adapter for Classic dock running indicators and activation
// intents. This component adds no Item, image, geometry, color, timer,
// animation or shortcut: it only projects a trusted WindowActivationState into
// fail-closed reads for a future dock wiring. DockTile.qml and main.cpp are
// owned by other workstreams; wiring is a documented dependency, not a change
// made here.
import QtQml

QtObject {
    id: activationIndicators

    property var state: null

    readonly property bool indicatorsAvailable: activationIndicators.state !== null
        && activationIndicators.state.backendTrusted === true
        && activationIndicators.state.status === "READY"

    readonly property var runningApps: indicatorsAvailable
        ? activationIndicators.state.runningApps : []

    readonly property var activeApps: indicatorsAvailable
        ? activationIndicators.state.activeApps : []

    function running(appId) {
        return indicatorsAvailable && activationIndicators.state.isRunning(appId)
    }

    function active(appId) {
        return indicatorsAvailable && activationIndicators.state.isActive(appId)
    }

    function activation(appId, originApp) {
        if (!indicatorsAvailable) {
            return "REJECT"
        }
        return activationIndicators.state.resolveActivation(appId, originApp)
    }
}
