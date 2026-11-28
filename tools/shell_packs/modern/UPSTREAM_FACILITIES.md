# Upstream facilities reused by Modern (definition-level inventory)

This is a design inventory, not proof that any facility is wired at runtime.
No upstream source code or proprietary asset is copied into this pack. The
canonical integration points must be verified against the target Plasma 6 /
KF6 release before runtime work starts.

| Concern | Reuse through the Canopy host | Pack must not |
| --- | --- | --- |
| Session / compositor | One KWin/Plasma session owned by the host; pack is a presentation only. | Start a second compositor or window manager. |
| Apps and launch | Host catalogue from upstream desktop entries / KDE application model; launch through the host's authorized path. | Build a second index or spawn commands from metadata. |
| Taskbar / windows | Host window and workspace model (e.g. upstream TasksModel), focus/minimize/restore through host authority. | Manufacture trusted window state or duplicate a task service. |
| Notifications / tray | Host-owned notification source and status items; upstream Plasma components where available. | Run a second notification daemon or tray service. |
| System status | Upstream power, network, Bluetooth, audio and display facilities exposed once by the host. | Poll hardware directly or keep a parallel status process. |
| Settings / accessibility | Shared host preferences, keyboard focus, screen-reader metadata, contrast, scaling and reduced motion. | Fork Classic preferences or bypass accessibility contracts. |

Unavailable upstream functionality must be shown as unavailable, not faked.
Community QML/JS remains disabled until provenance, signing, isolation and
capability enforcement exist; a valid manifest is not a trust decision.
