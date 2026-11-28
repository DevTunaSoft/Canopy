/*
 * Canopy Classic native task applet (M2 bounded port of PR #730).
 * Exactly one upstream TaskManager.TasksModel is declared here. The dock and
 * panel consumers receive that object by injection; no second model, no local
 * ListModel and no synthetic window facts exist in this package. Activation is
 * one request to the same upstream model; KWin performs the real focus change.
 */
import QtQuick
import org.kde.plasma.plasmoid
import org.kde.taskmanager as TaskManager

PlasmoidItem {
    id: canopyTasks
    property alias tasksModel: upstreamTasks

    TaskManager.TasksModel {
        id: upstreamTasks
        filterByScreen: true
    }

    readonly property int taskCount: upstreamTasks.count

    compactRepresentation: Item {
        width: 180
        height: 32
        Text {
            anchors.centerIn: parent
            color: "#f7f5eb"
            text: "Canopy tasks: " + canopyTasks.taskCount
        }
    }

    fullRepresentation: Column {
        spacing: 4
        Text {
            color: "#f7f5eb"
            text: "Canopy classic — upstream tasks (" + canopyTasks.taskCount + ")"
        }
        Repeater {
            model: canopyTasks.tasksModel
            delegate: Item {
                width: 260
                height: 26
                Text {
                    anchors.fill: parent
                    verticalAlignment: Text.AlignVCenter
                    color: model.isActive === true ? "#b0d6e8f6" : "#d6e8f6"
                    text: (model.display !== undefined ? model.display : "")
                          + (model.isWindow === true ? " [running]" : " [launcher]")
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        if (canopyTasks.tasksModel !== null)
                            canopyTasks.tasksModel.requestActivate(
                                canopyTasks.tasksModel.index(index, 0));
                    }
                }
            }
        }
    }
}
