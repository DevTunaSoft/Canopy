import QtQuick

// Canopy Modern presentation descriptor ONLY.
//
// This is a bounded, non-runnable QML placeholder for the first-party Modern
// Shell Pack. It is not a desktop, not a compositor and not an installed
// shell. The host owns the compositor/session, app catalogue and launch,
// native windows/workspaces, notifications, system status, settings and
// accessibility. Upstream Plasma/KF6 facilities are used through that host;
// this pack must never start a parallel daemon, index, timer or network task.
//
// No paid tier, activation check, account, advertisement or telemetry exists
// here. Approved Classic identity and assets are untouched by this pack.
Item {
    id: modernPresentationRoot
    objectName: "canopyModernPresentationDescriptor"
    implicitWidth: 1280
    implicitHeight: 720

    // No background activity: no Timer, no network, no service instance and
    // no pack-owned subscription. Visual layout is added only through a
    // separately reviewed host API and owner visual acceptance.
}
