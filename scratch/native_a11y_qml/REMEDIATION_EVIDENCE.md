# PR #752 HOLD remediation evidence

Scope of this commit: `docs/NATIVE_A11Y_QML_FIX.md`, `scratch/native_a11y_qml/**`,
and the two `RENDERED_VISUAL_SHA256` constants in
`tests/test_nd041_native_settings_controls_wiring.py` only. `PreviewWindow.qml`,
`Main.qml` (FD-581), `Theme.qml`, `CMakeLists.txt`, `main.cpp` and
`prototype/classic/assets/**` are untouched. No merge, no approval, no visual
source edit.

## HOLD causes closed

1. Foundation red from two stale ND-041 pins. Base digests:
   `SettingsPanel.qml = 38f1cf1512dff833dee7f8e1f844724682b2a1319bb3c798c501de0ebbbf192c`,
   `QuickControlsOverlay.qml = 257e00bb5f337495bcd46ba97c34cbdb33d68ac99566802e7bd92f0e4d4fd02b`.
   Synced to the owned-QML bytes at PR head `395cced`:
   `SettingsPanel.qml = e5520ba7705c453014148cc98d36f3a71e725f65f68150b644adca6d2dc2c1c5`,
   `QuickControlsOverlay.qml = 19349a4fdd952bc9a83d24ea644e5ea84dbd512ad9f2be1f76074c67dddcda0c`.
   Every added byte in those halves is an `Accessible.*` name/description line.
   The rendered-input projection (all `Accessible.*` lines stripped) is
   byte-identical to the base (`ed68156d…` and `752c7d59…`), so this is a
   test-only pin sync, not a visual change.
2. `verify_owned_a11y_qml.json` clean-checkout mismatch: the committed JSON was
   generated in a dirty tree (it counted the script's own string literals and
   doc lines as product edits). `verify_owned_a11y_qml.py` now scopes added-line
   checks to the four owned QML files and explicitly allows the two non-QML
   evidence paths (doc + scratch, plus the authorized ND-041 pin sync). The
   JSON is regenerated from a clean checkout of the remediation head.
3. False byte-frozen geometry claim: `32/96/14/7` is withdrawn. At this base
   `tests/test_classic_qt_source.py` pins `barHeight: 32`, `dockSize: 88`,
   `dockPadding: 12`, `dockSpacing: 7` — i.e. `32/88/12/7`.
4. `Alt+W` / `Alt+H` evidence is labelled source-gated plus compiled-load only.
   Qt CI at `395cced` compiled `ShellMenuBar.qml` into the qmlcache and the
   binary self-tests ran at 1920x1080 / 1200x750 / 760x500; neither shortcut
   nor Tab activation was exercised at runtime, so native reachability stays
   `NOT_RUN`.

## Commands and results at the remediation head

| Check | Command | Result |
| --- | --- | --- |
| Owned static gate | `python scratch/native_a11y_qml/verify_owned_a11y_qml.py` | PASS, 11/11, `all_pass: true` |
| ND-041 pin test | `python -m unittest tests.test_nd041_native_settings_controls_wiring` | PASS, 10 tests |
| Targeted QML contracts | `python -m unittest -v tests.test_classic_shell_menus tests.test_classic_shell_menu_polish tests.test_classic_premium_topbar_menu_da74616 tests.test_classic_status_a11y tests.test_classic_qt_source` | PASS, 42 tests |
| Accessibility patterns | `python -m unittest discover -s tests -p 'test_c100_accessibility_*.py'` | PASS, 132 tests |
| Extended wiring/keyboard | `python -m unittest tests.test_c100_classic_keyboard_accessibility tests.test_classic_keyboard_accessibility_gate tests.test_classic_clock_accessibility_no_visual_change tests.test_nd041_native_settings_controls_wiring tests.test_classic_source` | PASS, 62 tests |
| Foundation contract | `python tools/check_foundation.py` | PASS |
| Foundation regression | `python -m unittest discover -s tests` | see `docs/NATIVE_A11Y_QML_FIX.md` |

No native AT-SPI, screen-reader, owner visual acceptance or release-ready claim
is made here.
