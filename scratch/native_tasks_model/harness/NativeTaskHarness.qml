import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.taskmanager as TaskManager

// Native Classic task-dock harness. It declares the ONLY TaskManager.TasksModel
// in this process, following PR #730's bounded single-model pattern. The frozen
// Canopy DockTile.qml is reused byte-for-byte; running/active dots are derived
// from the injected upstream model by NativeTaskBoard. Activation goes straight
// back to that same model's requestActivate(): no second model, no duplicate
// launcher, no synthetic window state and no local process launch.
ApplicationWindow {
    id: root
    objectName: "canopyNativeTaskHarness"
    width: 1100
    height: 640
    visible: true
    title: "Canopy Classic native task dock"
    color: "#1f2326"

    readonly property string terminalId: "konsole"
    property int phase: 0

    TaskManager.TasksModel {
        id: upstreamTasks
        filterByScreen: true
        separateLaunchers: true
        // Favorites are applied after model completion (below): TasksModel
        // loads its KConfig launcher list during construction, so an inline
        // binding is reset before Component.onCompleted runs.
    }

    Component.onCompleted: {
        console.log("CANOPY_NATIVE_TASK_MODEL_INFO count=" + upstreamTasks.count
                    + " launcherCount=" + upstreamTasks.launcherCount);
        const attached = canopyNativeTasks.attachModel(upstreamTasks);
        console.log("CANOPY_NATIVE_TASK_ATTACH", attached ? "PASS" : "FAIL");
    }

    function activateTile(appId) {
        let row = canopyNativeTasks.rowFor(appId);
        let kind = "focus";
        if (row < 0) {
            row = canopyNativeTasks.launcherRowFor(appId);
            kind = "launch";
        }
        if (row < 0) {
            canopyNativeTasks.logEvent("REFUSE no live or launcher row for " + appId);
            return false;
        }
        canopyNativeTasks.logEvent("REQUEST " + kind + " " + appId + " row=" + row);
        upstreamTasks.requestActivate(upstreamTasks.index(row, 0));
        return true;
    }

    // Test-driver only: deterministic phase markers so a headless SSH harness
    // can prove a real upstream launch and a real upstream activation without
    // simulating any window. No timer exists in the adapter itself.
    Timer {
        id: driver
        interval: 1500
        repeat: true
        running: autoSequence && root.phase < 18
        onTriggered: {
            root.phase += 1;
            if (root.phase === 3)
                canopyNativeTasks.logEvent("PHASE 3 native app launch observed upstream");
            if (root.phase === 14) {
                canopyNativeTasks.logEvent("PHASE 14 upstream window activation");
                root.activateTile(root.terminalId);
            }
            if (root.phase === 18)
                canopyNativeTasks.logEvent("PHASE 18 observation complete");
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 18

        Text {
            Layout.fillWidth: true
            color: "#f7f5eb"
            font.pixelSize: 22
            text: "Canopy Classic — native Plasma tasks"
        }
        Text {
            id: stateLabel
            objectName: "canopyTaskState"
            Layout.fillWidth: true
            color: "#b0d6e8f6"
            font.pixelSize: 16
            text: "model rows=" + upstreamTasks.count
                  + " | running=" + JSON.stringify(canopyNativeTasks.runningApps)
                  + " | active=" + JSON.stringify(canopyNativeTasks.activeApps)
        }
        Text {
            id: rowLabel
            objectName: "canopyTaskRows"
            Layout.fillWidth: true
            color: "#d6e8f6"
            font.pixelSize: 13
            wrapMode: Text.Wrap
            text: "upstream rows: " + upstreamTasks.count
        }
        Item { Layout.fillHeight: true }

        Row {
            Layout.alignment: Qt.AlignHCenter
            spacing: 12

            Repeater {
                model: [
                    { title: "Browser", id: "firefox" },
                    { title: "Files", id: "org.kde.dolphin" },
                    { title: "Photos", id: "org.kde.gwenview" },
                    { title: "Settings", id: "kdesystemsettings" },
                    { title: "Terminal", id: "konsole" }
                ]
                delegate: DockTile {
                    required property var modelData
                    objectName: "canopyNativeTile_" + modelData.id
                    iconName: modelData.title
                    // The frozen tile's existing 5px dot becomes the real
                    // running indicator; no tile byte is changed.
                    previewActive: canopyNativeTasks.isRunning(modelData.id)
                    onActivated: function(applicationName) {
                        root.activateTile(modelData.id);
                    }
                }
            }
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            color: "#8fa9bf"
            font.pixelSize: 12
            text: "One upstream TaskManager.TasksModel; activation via requestActivate()"
        }
    }
}
