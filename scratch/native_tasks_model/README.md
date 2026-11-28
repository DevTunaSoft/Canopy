# Native TasksModel M2 scratch package

Read `../../docs/NATIVE_TASK_MODEL.md` first. This directory is the owned
scratch implementation and evidence for the bounded PR #730 port.

## Layout

* `src/NativeTaskBoard.*` — read-only, event-driven projection of one injected
  upstream model; `src/board_probe.cpp` — compiled negative controls.
* `harness/` — real-session QML harness; `DockTile.qml` is a byte-identical copy
  of `prototype/classic/DockTile.qml`.
* `icons/` — byte-identical copies of the approved Classic dock SVG bytes.
* `package/` — reversible user-scope Plasma/Applet KPackage.
* `tests/` — offline source-contract gates.
* `scripts/guest_runtime.py` — SSH driver against the existing Plasma 6 guest.
* `evidence/` — raw logs, real screenshots, `SHA256SUMS` and `runtime_report.json`.

## Reproduce

Host (offline gates):

```sh
cd <worktree>
python3 -m unittest discover -s scratch/native_tasks_model/tests -v
PYTHONPATH=. python3 -m unittest tests.test_classic_dock_frozen \
  tests.test_check_visual_lock tests.test_classic_window_activation_host \
  tests.test_pe080_native_catalog_integration_boundary -v
```

Guest (requires the pre-provisioned SSH key and Plasma VM from the existing
reference environment):

```sh
python3 scratch/native_tasks_model/scripts/guest_runtime.py \
  stage board runtime package
```

The driver confines writes to
`/home/canopy/canopy_native_tasksmodel_m2`, performs no VM control action,
unlocks the existing seat session only for screenshot visibility, and removes
its guest directory after the evidence is copied. The KPackage is installed and
then removed with `kpackagetool6`; plasma config hashes are recorded before and
after.

No command here merges, approves or promotes a PR.
