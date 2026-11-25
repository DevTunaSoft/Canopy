// Non-visual host adapter for Classic dock running indicators and activation
// intents. This component adds no Item, image, geometry, color, timer,
// animation or shortcut: it only projects a trusted WindowActivationState into
// fail-closed reads. The compiled shell instantiates it in main.cpp and binds
// its state-derived properties into DockTile.qml text/accessibility only.
import QtQml

QtObject {
    id: activationIndicators

    property var state: typeof canopyWindowActivationState !== "undefined"
        ? canopyWindowActivationState : null

    readonly property int sequence: indicatorsAvailable ? state.sequence : -1

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
