/*
 * Dock/panel task delegate. Reads upstream TaskManager roles only.
 * Activation is one advisory request routed through TasksModel.requestActivate;
 * KWin/TaskManager performs the real focus change. No X11/Wayland call, no
 * process launch and no synthetic success token exists in this delegate (A02, A04).
 */
import QtQuick
import QtQuick.Accessibility
import org.kde.plasma.components as PlasmaComponents

Item {
    id: taskDelegate
    property var tasksModel: null
    width: 48
    height: 48

    PlasmaComponents.ToolButton {
        anchors.fill: parent
        // Icon comes from the upstream task/decoration role; approved Canopy
        // icons are supplied by the icon theme (R10, R11, R14, A19).
        icon.name: model.decoration !== undefined ? model.decoration : ""
        checked: model.active === true
        Accessible.name: model.display !== undefined ? model.display : ""

        onClicked: {
            if (taskDelegate.tasksModel !== null)
                taskDelegate.tasksModel.requestActivate(taskDelegate.tasksModel.index(index, 0))
        }
    }
}
