// Compiled-QMl behavioural checks for the non-visual adapter.
// The host harness sets `adapter` to a WindowActivationIndicators instance and
// calls checkUntrusted/checkReady/checkCleared at the matching snapshot phase.
import QtQml

QtObject {
    function checkUntrusted() {
        var fails = []
        if (adapter.indicatorsAvailable) fails.push("untrusted:available")
        if (adapter.runningApps.length !== 0) fails.push("untrusted:runningApps")
        if (adapter.activeApps.length !== 0) fails.push("untrusted:activeApps")
        if (adapter.running("Files")) fails.push("untrusted:running")
        if (adapter.active("Files")) fails.push("untrusted:active")
        if (adapter.activation("Files", "Canopy") !== "REJECT") fails.push("untrusted:activation")
        return fails.join(",")
    }

    function checkReady() {
        var fails = []
        if (!adapter.indicatorsAvailable) fails.push("ready:available")
        if (!adapter.running("Files")) fails.push("ready:running")
        if (adapter.running("Browser")) fails.push("ready:runningBrowser")
        if (!adapter.active("Files")) fails.push("ready:active")
        if (adapter.activation("Files", "Canopy") !== "FOCUS") fails.push("ready:focus")
        if (adapter.activation("Browser", "Canopy") !== "LAUNCH") fails.push("ready:launch")
        if (adapter.activation("Files", "Mail") !== "REJECT") fails.push("ready:crossAppDenied")
        if (adapter.activation("Settings", "Canopy") !== "REJECT") fails.push("ready:missing")
        return fails.join(",")
    }

    function checkCleared() {
        var fails = []
        if (adapter.indicatorsAvailable) fails.push("cleared:available")
        if (adapter.runningApps.length !== 0) fails.push("cleared:runningApps")
        if (adapter.activeApps.length !== 0) fails.push("cleared:activeApps")
        if (adapter.running("Files")) fails.push("cleared:running")
        if (adapter.active("Files")) fails.push("cleared:active")
        if (adapter.activation("Files", "Canopy") !== "REJECT") fails.push("cleared:activation")
        return fails.join(",")
    }
}
