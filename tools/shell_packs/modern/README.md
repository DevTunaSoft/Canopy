# Modern Shell Pack (first-party, bounded definition)

Status: **metadata + non-runnable QML descriptor only**. There is no Modern
runtime loader, no installed shell and no visual approval here. This directory
is an original Canopy definition; it does not copy Classic artwork or any
third-party layout.

## Identity

- Built-in identity in the Canopy core: `org.canopy.modern` (reserved, free).
- On-disk Shell Pack v1 manifest id: `io.canopy.modern`.
  The existing offline checker (`tools/check_shell_pack.py`) rejects the
  `org.canopy.` built-in namespace for catalog manifests, so the first-party
  on-disk descriptor uses a non-reserved id. The binding between these two
  identities is explicit and data-only in
  `canopy_features/settings/shell_pack_manifest.py`.
- Presentation only, `shell_api: 1`, `ui_engine: qt-qml`,
  `switch_strategy: same-session` (an intent, not proof that a live switch
  works). `permissions` is empty.

## Shared core and upstream reuse

The definition requests UI affordances from the host only: application
launcher, taskbar, workspace list, window list, system status and settings
panel. Those are not privileges and not services. One Canopy core owns the
compositor/session integration and the single instance of each shared
service. Modern reuses upstream Plasma 6/KF6 facilities through that core:
TasksModel/windows, application discovery and desktop entries, notifications,
tray/system status, power/network/audio, display and accessibility. It must
not fork them or start a second compositor, notification daemon, app index,
settings service or always-on helper. See `UPSTREAM_FACILITIES.md`.

## Free and open

All first-party packs are included at no cost. There is no paid edition,
unlock, subscription, activation, account, advertisement or mandatory
telemetry. The manifest carries no endpoint, purchase or activation field.

## Lifecycle boundary

`canopy_features/settings/shell_pack_manifest.py` models prepare/apply/
verify/rollback as a pure, bounded bookkeeping ledger. It reads only this
manifest and never loads `ui/Main.qml`, starts a process, writes settings,
changes a session or contacts a network. A real switch requires the reviewed
host lifecycle and compatibility gates; it is explicitly NOT_RUN here.
