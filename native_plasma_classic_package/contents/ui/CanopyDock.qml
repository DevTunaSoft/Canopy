/*
 * Canopy Classic centered floating dock - PlasmoidItem applet representation.
 * Favorites come from the upstream launcher configuration (KConfig), not a
 * second Canopy favorites store.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents

PlasmoidItem {
    id: canopyDock

    property var tasksModel: null

    compactRepresentation: PlasmaComponents.Label {
        text: "Canopy Classic dock"
    }

    fullRepresentation: RowLayout {
        // Approved dock order is supplied by upstream favorites; no local
        // ListModel or hand-built row set is used here.
        Repeater {
            model: canopyDock.tasksModel
            delegate: TaskDelegate {
                tasksModel: canopyDock.tasksModel
            }
        }
    }
}
