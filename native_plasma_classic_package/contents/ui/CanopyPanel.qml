/*
 * Canopy Classic native top panel - PlasmoidItem applet representation.
 * No synthetic window rows, no Canopy-owned compositor, shell or service process.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.taskmanager as TaskManager

PlasmoidItem {
    id: canopyPanel

    property alias tasksModel: upstreamTasks
    TaskManager.TasksModel {
        id: upstreamTasks
        screenGeometryFilter: true
    }

    // Projection only: a count is never used as a fabricated window record.
    readonly property int taskCount: upstreamTasks.count

    compactRepresentation: PlasmaComponents.Label {
        text: "Canopy Classic"
    }

    fullRepresentation: RowLayout {
        Repeater {
            model: canopyPanel.tasksModel
            delegate: TaskDelegate {
                tasksModel: canopyPanel.tasksModel
            }
        }
    }
}
