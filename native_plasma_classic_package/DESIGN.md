# Canopy Classic — native Plasma 6 KPackage scaffold (DESIGN)

**Scope:** `DESIGN_AND_STRUCTURE_ONLY;NO_COMPILE;NO_RUNTIME;NO_VISUAL_APPROVAL;NO_REPO_MUTATION`. No binary, no guest boot, no desktop acceptance, no screenshot approval. All files live only in `C:/Users/X1/AppData/Local/hermes/cache/scratch/native_plasma_classic_package/`.

**Source pin:** tag `archive/canopy-classic-final-20261127-fef38c3` → commit `fef38c311736b7cdded3acedde4bae985237a6e3`, tree `0f128ea10dfe78e2286a7792b4b5d0557c21047b`.
**Grounding:** `native_plasma_reuse_inventory.md` (23 REUSE / 30 ADAPT / 9 LEGACY_ONLY) and `native_plasma_baseline_readiness.md` (KF6/Plasma6 dev packages, native session and one-compositor proof are `NOT_RUN`/guest-blocked on this host).
**Upstream provenance:** KDE "Porting Plasmoids to KF6" and "Setup" (develop.kde.org/docs/plasma/widget/), KWin 6 scripting API, `TaskManager::TasksModel`, freedesktop Notifications / Status Notifier / logind specs. API versions must be re-verified on the reference guest; none is claimed verified here.

## 1. Structural rules encoded in this package

- `metadata.json`: `KPackageStructure: "Plasma/Applet"`, `X-Plasma-API-Minimum-Version: "6.0"`, `X-Plasma-ContainmentType: "Desktop"`, `KPlugin.Version: "0.1.0"`. No `X-Plasma-MainScript`, `X-Plasma-API` or `ServiceTypes` (KF6 porting rule). `contents/ui/main.qml` is the only entry point.
- `contents/ui/main.qml` root is `ContainmentItem` (QML front-end to `ContainmentInterface`); `CanopyPanel.qml` and `CanopyDock.qml` roots are `PlasmoidItem`. The legacy standalone application-window shell root is explicitly excluded (A17, A24, L05).
- All QML imports are un-versioned, as required by Qt6/KF6; no `ListModel` fabricates running windows.
- **One compositor and shared services:** with one compositor (KWin) and `plasmashell` as the only shell, this package guarantees one compositor and shared upstream services. KWin is the only compositor, `plasmashell` the only shell. This package spawns no compositor, shell, notification daemon, tray/status daemon, network/power listener or second application index.
- Asset references are hash-only (see `ASSET_BINDINGS.json`); no approved bytes are copied, decoded, recompressed or modified. Legacy blue-wave assets are denylisted (L09).

## 2. Component → upstream API map

| Scaffold component / concern | Inventory IDs | Upstream owner (mature API) | Port rule |
|---|---|---|---|
| `main.qml` `ContainmentItem` root | A01, A17, A24 | Plasma `Containment`/`ContainmentInterface` + KPackage metadata; `plasmashell` lifecycle prepare/activate/deactivate/dispose | One active Canopy containment per screen; no second shell or compositor |
| `CanopyPanel.qml` `PlasmoidItem` | A06, A18 | Plasma `Applet`/`PlasmoidItem`, `PlasmaCore.Action` contextual actions, KRunner/Kickoff launcher | Compact/full representations only; no frozen geometry, colour or typography change |
| `CanopyDock.qml` `PlasmoidItem` | A03, A04, A19 | `TaskManager::TasksModel` + `StartupTasksModel`, `activeTask`, upstream launcher favorites via KConfig | Single task model and favorites store; approved dock order/icons preserved |
| `TaskDelegate.qml` | A02, A04, A25 | `TasksModel` roles (`decoration`, `active`, `display`) and `requestActivate`; KWin `Workspace`/`Window` focus | Advisory, single-use activation; no X11/Wayland call, no process launch |
| Wallpaper binding | R07, R14, A16 | Plasma wallpaper containment plugin + exact approved PNG blob | Hash-only reference; zero new wallpaper artwork |
| Icons and Tux mark | R10, R11, R14, A19 | Upstream icon theme fed by approved originals; `tools/check_wallpaper.py` byte gates | No redesign, recoloring, recompression or substitution |
| Notifications | R16, A11, A30 | Single `org.freedesktop.Notifications` session server; Plasma `NotificationManager::Notifications` model | No Canopy-owned notification daemon; real rows only from upstream model |
| Tray / quick controls | R18, A12, A22 | Plasma System Tray applets: network, Bluetooth, audio, brightness, power | Fail-closed projections; upstream applets own devices and D-Bus |
| Session / lock / power | R08, R17, A13 | `org.kde.Shutdown` then `org.freedesktop.login1`; ksmserver | No raw command path; fail closed on absent observations |
| Window / workspace / display | A05, A14 | KWin `Workspace`, `Window`, `clientArea`, `Output`, `VirtualDesktop`, `TileManager` | Read-only decision records; geometry changes frozen pending owner approval |
| Launch / files / desktop actions | A06–A10, A26 | `KRun`, `KService`, `KIO`, xdg portal, startup notification | Keep bounded validators; upstream performs launch; no GIO daemon duplicate |
| Catalog and search | R05, A07, A21 | `KSycoca`/`KService` change notification | Zero Canopy-owned `*.desktop` index files |
| Host event contract | R01, R02, R12, A23 | In-process contract only; upstream Qt/D-Bus signals feed a bounded KF6 plugin dispatcher | Four-topic allowlist and 64-event cap retained; no second event loop |
| Accessibility | R04, R13, A06 | Qt style hints and Plasma accessibility settings | Pure validators; screen-reader runtime is `NOT_RUN` until separately exercised |
| Settings and trusted packs | R03, A15, A28 | KPackage metadata, KConfig, trusted built-in packs; ownership-aware install | One active presentation; reversible install with byte-identical restore |
| Legacy-only families | L01–L09 | Mint/Cinnamon comparison lane, fake-GIO fixtures, standalone preview, blue-wave art | Excluded from the native package; never used as native acceptance evidence |

## 3. Explicit boundaries and later gates

`COMPILE_NOT_RUN`, `RUNTIME_NOT_RUN`, `VISUAL_APPROVAL_NOT_RUN`, `RELEASE_NOT_RUN`, `AWAITING_OWNER_FINAL_VISUAL_ACCEPTANCE`. Acceptance checks (one `kwin_*` and one `plasmashell` tree, one notifications owner, real `TasksModel` rows from a real launch, reversible install, 5-minute idle PSS/CPU) remain deferred to a real Plasma 6 guest at a pinned native tip; green static checks here are not acceptance. Approved identity, wallpaper, icons, dock geometry and typography stay frozen.
