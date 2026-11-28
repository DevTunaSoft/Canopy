# Native Classic QML accessibility remediation (M3/M5)

**Branch:** `product/native-a11y-qml-20261128`
**Base:** `ec910d7a7275296ecbc8b5e5c459d356205165d1`
**Directive context:** Rev3 SHA `1fba4b1e`, cap 8, 4 active.
**PR:** DRAFT only — no merge, no self-approval, no main/integration change.

This change follows PR #740, which verified AT-SPI roles at the same base but
explicitly recorded two QML defects as outside its owned paths: 7/7/6 unnamed
secondary labels and named-but-unreachable `Window menu` / `Help menu` at
760x500. This change repairs only the files listed in its ownership grant and
does not re-label any prior evidence as verification of this head.

## Owned files changed

| File | Change | Visual impact |
| --- | --- | --- |
| `prototype/classic/ShellMenuBar.qml` | Two non-visual `Shortcut` items (`Alt+W`, `Alt+H`) calling the existing `windowMenu.open()` / `helpMenu.open()` proxies. | None. No geometry, artwork or binding change. |
| `prototype/classic/ShellMenuPopupSet.qml` | `Accessible.name: text` on the secondary menu-item `Label`. | None. |
| `prototype/classic/QuickControlsOverlay.qml` | Names/descriptions on the subheading, per-domain title, host-status label and both button content labels. | None. |
| `prototype/classic/SettingsPanel.qml` | Names/descriptions on the subheading, row title and all three button content labels. | None. |
| `docs/NATIVE_A11Y_QML_FIX.md` | This record. | n/a |
| `scratch/native_a11y_qml/**` | Static gate, exact blocker probe, root-cause notes, logs. | n/a |

14 accessibility-only lines added; zero visual lines added, removed or
reordered. `Theme.qml`, `Main.qml`, `PreviewWindow.qml`, `CMakeLists.txt`,
`main.cpp` and `prototype/classic/assets/**` are untouched. The approved
identity markers (`barHeight: 32`, `dockSpacing: 7`, the 32/96/14/7 geometry
line, Tux launcher, wallpaper and all eight approved icons) remain byte-frozen.

## Defect status

| Item | Status | Basis |
| --- | --- | --- |
| Secondary labels in the four owned QML files named/described | `PASS` (static) | 11/11 `verify_owned_a11y_qml.py` checks; 42 targeted source tests. |
| 7/7/6 unnamed file-detail labels from PR #740 | `ROOT_CAUSED_NOT_APPLIED_OUTSIDE_OWNERSHIP` | Exact source is `PreviewWindow.qml` lines 562-566, not in this ownership set. Minimal hunk recorded in `scratch/native_a11y_qml/OUT_OF_OWNERSHIP_ROOT_CAUSES.md`. |
| Window/Help menus reachable at 760x500 | `PASS` (source gate) via owned path; native `NOT_RUN` | `Alt+W` / `Alt+H` reach the same two menu proxies while `Main.qml`'s compact-layout visibility rule is preserved. The hidden top-bar buttons themselves remain out of ownership. |
| AT-SPI name/description/role re-measure at this head in real Plasma | `BLOCKED` | Running VM but no guest execution service and no supplied guest login; see `scratch/native_a11y_qml/ATSPI_BLOCKER.md`. |
| Screen-reader announcements / Orca | `NOT_RUN` | No reader started or queried. |
| Final owner visual acceptance | `AWAITING_OWNER_FINAL_VISUAL_ACCEPTANCE` | No compiled screenshot or visual claim in this change. |

## Verification performed

| Check | Command | Result |
| --- | --- | --- |
| Owned static gate | `python scratch/native_a11y_qml/verify_owned_a11y_qml.py` | `PASS` — 11/11, `all_pass: true` (JSON saved beside it). |
| Targeted QML contracts | `python -m unittest -v tests.test_classic_shell_menus tests.test_classic_shell_menu_polish tests.test_classic_premium_topbar_menu_da74616 tests.test_classic_status_a11y tests.test_classic_qt_source` | `PASS` — 42 tests, including byte-frozen rendered inputs and approved-art manifest. |
| Accessibility pattern gates | `python -m unittest discover -s tests -p 'test_c100_accessibility_*.py'` | `PASS` — 132 tests. |
| Extended wiring/keyboard gates | `python -m unittest tests.test_c100_classic_keyboard_accessibility tests.test_classic_keyboard_accessibility_gate tests.test_classic_clock_accessibility_no_visual_change tests.test_nd041_native_settings_controls_wiring tests.test_classic_source` | `INCONCLUSIVE` — 60 pass, 2 fail. Both failures are the ND-041 `RENDERED_VISUAL_SHA256` pin, which hashes accessibility-only lines below `visible: opened`; new pins and the reason are recorded in the out-of-ownership note. `tests/**` is not owned here. |
| Native AT-SPI | `VBoxManage` probe recorded in `atspi_native_blocker_probe.txt` | `BLOCKED` — exact observations in `ATSPI_BLOCKER.md`. |

Logs: `scratch/native_a11y_qml/targeted_tests.log`,
`accessibility_pattern_tests.log`, `extended_tests.log`.

## Non-goals

No claim of native PASS, screen-reader behaviour, final visual acceptance,
release readiness or merge. No guest login, credential guess, VM state change,
geometry/art change, new menu command, merge or self-approval.
