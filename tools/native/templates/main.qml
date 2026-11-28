/*
 * Canopy Classic - development-baseline Plasma 6 applet.
 * One compositor (KWin) and one shell (plasmashell) own the desktop; this
 * applet creates neither. It carries the pinned binary/asset identity only.
 * No desktop-identity change, no release or visual approval claim.
 */
import QtQuick
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: canopyBaseline
    switchWidth: -1
    switchHeight: -1

    readonly property string packageId: "org.kde.plasma.canopyclassic"

    compactRepresentation: Item {
        implicitWidth: 16
        implicitHeight: 16
    }

    fullRepresentation: Item {
        implicitWidth: 1
        implicitHeight: 1
    }
}
