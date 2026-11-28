# Native Classic task model — bounded PR #730 port (M2)

Status: **NATIVE RUNTIME PASS for the bounded task-dock harness**. This is not
final M2 desktop acceptance, not owner visual approval and not a claim that the
whole Classic presentation is complete. Owner directive
`79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083`; base commit
`ec910d7a7275296ecbc8b5e5c459d356205165d1`.

## What was delivered

* A reversible user-scope Plasma 6 KPackage (`package/`, id
  `org.kde.plasma.canopyclassic.nativetasks`) that ports PR #730's **single
  authoritative `TaskManager.TasksModel`** pattern: one model declaration,
  injected by alias into every consumer, no local `ListModel`, no second task
  source, activation only through the same model's `requestActivate()`.
* A read-only C++ projection (`src/NativeTaskBoard.*`) that accepts **one**
  injected upstream model, derives event-driven running/active facts from its
  published roles, refuses a second model or malformed rows, and never polls,
  launches, opens a socket, walks the desktop or creates a model.
* A real-session harness (`harness/`) that reuses the byte-identical frozen
  `DockTile.qml` and original dock SVG bytes. The tile's existing 5 px dot is
  bound to the upstream-derived running fact; no approved visual source is
  edited.
* Offline source gates plus an in-guest compiled negative-control probe
  (`tests/`, `src/board_probe.cpp`).

### Adaptation, not a blind retarget

PR #730 was static-only and targeted the legacy integration branch. Two of its
assumptions do not survive contact with Plasma 6.6 in the reference guest:

| PR #730 text | Observed Plasma 6.6 API | Adaptation here |
| --- | --- | --- |
| `screenGeometryFilter: true` | property is `filterByScreen` (QML load failed on the original token) | use `filterByScreen: true` |
| "favorites come from upstream KConfig" | a harness-created `TasksModel` has an empty `launcherList`; assigning it does not persist | do not invent launcher rows; launch the app with native GIO for the runtime proof and track/focus the resulting live window |

No legacy branch commits, no native package from another worker and no stacked
branch were merged or retargeted. The upstream model, KWin and GIO remain the
only sources of desktop truth.

## Owned and frozen paths

Owned: `prototype/classic/LauncherModel.cpp/.h`, `WindowActivationState.cpp/.h`,
`DockTile.qml`, this document and `scratch/native_tasks_model/**`.

The four product files above are byte-frozen by `tests/test_classic_dock_frozen.py`
and `tests/test_classic_window_activation_host.py`, so this port deliberately
leaves them **byte-identical** and puts the native adapter/package under the
owned scratch path. `scratch/native_tasks_model/harness/DockTile.qml` and
`icons/*.svg` are verified byte-identical copies, not edits.

## Runtime evidence (`NATIVE RUNTIME`)

Guest: existing `Canopy-Test-Plasma6` VM, Ubuntu 26.04, Plasma 6.6.7, KWin X11
session, user `canopy`, SSH key forward `127.0.0.1:2223`. No VM start/stop,
snapshot or persistent user-config change. `xvfb` was installed only as a
diagnostic during setup and the abandoned nested session was terminated before
the accepted run; the accepted run used the real SDDM Plasma session
(`plasmashell` PID from `/proc`, KWin `kwin_x11`, Plasma bottom panel visible in
screenshots).

Driver: `scratch/native_tasks_model/scripts/guest_runtime.py`; raw logs and
screenshots in `scratch/native_tasks_model/evidence/`; summary in
`evidence/runtime_report.json`.

| Check | Command / evidence | Result |
| --- | --- | --- |
| Build | `cmake -GNinja -S . -B build && cmake --build build` in guest (`logs/stage_06_verify.log`) | PASS, both executables built |
| Compiled negative controls | `native-task-board-probe` (`logs/board_probe.log`) | `BOARD_ALL_PASS`: one model attaches, second model refused, launcher row not a running claim, removal/detach fail closed |
| Single model in sources | `tests/test_native_task_model_source.py` (6 offline tests) | PASS |
| Real app launch | `gio launch /usr/share/applications/org.kde.konsole.desktop` (`logs/runtime_02_launch_app.log`) | PASS, `/usr/bin/konsole` PID observed, Konsole window `~ : bash — Konsole` in `wmctrl -lp` |
| Running tracking | harness `CANOPY_NATIVE_TASK_SNAPSHOT` lines in `logs/runtime_03_running_observe.log` / `runtime_04_activation_observe.log` | PASS, `"running":["canopy-classic","konsole","native-task-harness"]`, visible dot on the Terminal tile in `evidence/runtime_focused.png` |
| Activation | focus stolen to harness (`xdotool windowactivate`), then `upstreamTasks.requestActivate(index)` | PASS, log `REQUEST focus konsole row=2`; active window changes from `Canopy Classic native task dock` to `~ : bash — Konsole`, and snapshot reports `"active":["konsole"]` |
| Install / uninstall | `kpackagetool6 --type Plasma/Applet --install/--remove` (`logs/package_02_install.log`, `package_06_remove.log`) | PASS (`INSTALL_RC=0`, `REMOVE_RC=0`); package appears then disappears from `--list`; plasma config SHA-256 unchanged before/after |
| Cleanup | `logs/cleanup.log` | PASS, guest scratch dir removed, package absent, no harness/Konsole process left by this task |

Screenshots (real 1920×1080 `scrot` captures from the live session):

* `evidence/runtime_focused.png` — SHA-256
  `88ed3decf1eb4e03f05f8d4e20e822cb0d1b0a9d0e0612abf5a4210405ab2892`; state
  text reads `model rows=3 | running=["canopy-classic","konsole","native-task-harness"] | active=["native-task-harness"]`.
* `evidence/runtime_running.png` — SHA-256
  `9c39aef71bf921ac2ca0b81faf456a0c890b8897e2dae633ccc309441cebb3bb`.
* `evidence/runtime_activated.png` — SHA-256
  `be665350a31ea2c2ad3515af1c0dc3c433c051282d59ae57deb9cc6c9446aa4b`;
  Konsole is the active window after the upstream activation request.

## Boundaries and honest labels

* `NATIVE RUNTIME`: compiled C++ ran in a real Plasma X11 session against the
  live upstream `TaskManager.TasksModel` and a real KWin-managed app window.
* `SYNTHETIC`: the auto sequence in the harness and the fake model in
  `board_probe.cpp` are deterministic test drivers; they do not imitate desktop
  facts.
* `NOT RUN`: full M2 presentation (approved wallpaper, top bar, keyboard
  navigation, package added to a permanent panel), resource/PSS/CPU budgets,
  screen-reader verification, Wayland, and owner final visual acceptance.
* No merge, approval, promotion or release action is requested by this change.
