import QtQuick

// Canopy Touch presentation descriptor ONLY.
//
// This is a bounded, non-runnable QML placeholder for a first-party Shell
// Pack. It is not a desktop, not a compositor and not an installed shell.
// The shared host owns the compositor/session, app catalogue and launch,
// windows/workspaces, notifications, status, settings and accessibility.
// This descriptor starts no parallel background work and owns no service.
//
// All first-party packs are included at no cost; no entitlement check or
// measurement endpoint is represented here. Approved Classic identity and
// assets are untouched by this pack.
Item {
    id: touchPresentationRoot
    objectName: "canopyTouchPresentationDescriptor"
    implicitWidth: 1280
    implicitHeight: 720

    // Inert data only: no scheduled callbacks, network clients, loaders or
    // service instances. Visual layout requires separate review and owner
    // visual acceptance.
}
