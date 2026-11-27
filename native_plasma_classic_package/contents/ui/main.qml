/*
 * Canopy Classic - native Plasma 6 desktop containment root.
 * STRUCTURAL SCAFFOLD ONLY: no compiled runtime, no desktop acceptance, no visual approval.
 * One compositor: KWin. One shell: plasmashell. This file creates neither.
 * The legacy standalone-window shell root (A17, L05) is deliberately absent.
 */
import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

ContainmentItem {
    id: canopyDesktop

    // KF6: the root is ContainmentItem (QML front-end to ContainmentInterface);
    // `plasmoid` is the underlying C++ Containment, not a wrapper (A01, A17).
    readonly property string canopyPackageVersion: "0.1.0"

    // Approved wallpaper identity is bound by ASSET_BINDINGS.json via SHA-256.
    // Runtime owner: the Plasma wallpaper containment plugin (R07, R14, A16).
    // No Image{} is created here and no approved asset bytes live in this package.

    // Native top panel and centered floating dock are separate applets loaded by
    // plasmashell from their own KPackage metadata; only their structural shape
    // is declared here (A01, A03, A06, A24).
    CanopyPanel {
        id: canopyTopPanel
        anchors {
            left: parent.left
            right: parent.right
            top: parent.top
        }
    }

    CanopyDock {
        id: canopyFloatingDock
        tasksModel: canopyTopPanel.tasksModel
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
    }
}
