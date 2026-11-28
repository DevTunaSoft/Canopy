# Out-of-ownership root causes — prepared, NOT applied

Two defects reported by PR #740 originate in QML files that are **not** in
this change's ownership set. They are recorded here with exact locations and
minimal proposed hunks so the owning workstream can apply them. No hunk in
this document was applied to any repository file.

## D1 — 7/7/6 unnamed secondary file-detail labels

- Exact source: `prototype/classic/PreviewWindow.qml` lines 562-566, second
  `Label` in `delegate: Item { objectName: "canopyFileRow" }`, binding
  `text: isDir ? "" : size + " B"`.
- Evidence: in `a11y_summary.json` at 1920x1080 / 1200x750 / 760x500 the
  unnamed `label` nodes (7 / 7 / 6; 20 `EMPTY_NAME` total in the gate) follow
  folder rows, where `isDir === true` makes the secondary label's text empty.
- Proposed minimal, non-visual hunk (NOT APPLIED — file not owned here):

```diff
                         Label {
                             text: isDir ? "" : size + " B"
                             color: "#8292a3"
                             font.pixelSize: 10
+                            Accessible.ignored: isDir
                         }
```

- Alternative, mutually exclusive, if every exposed label must carry a name:
  `Accessible.name: isDir ? "Folder — no size" : size + " B"`. Not recommended.

## D2 — named-but-unreachable Window/Help menus at 760x500

- Exact source: `prototype/classic/Main.qml` lines 172-173, delegate of the
  six-menu `Repeater`: `visible: !root.compactLayout || (modelData !== "Window" && modelData !== "Help")`.
- Evidence: at 760x500 the buttons named `Window menu` and `Help menu` are in
  the AT tree with `extents: null`, while File/Edit/View/Go have real extents.
- This change restores **reachability** inside the owned `ShellMenuBar.qml`
  with non-visual `Alt+W` / `Alt+H` shortcuts that call the existing
  `windowMenu.open()` / `helpMenu.open()` proxies; `Main.qml` is untouched.
- Alternative hunk if the owning workstream prefers to stop advertising the
  hidden buttons instead (NOT APPLIED — file not owned here):

```diff
                     Accessible.name: modelData + " menu"
                     Accessible.description: "Open the " + modelData + " menu"
+                    Accessible.ignored: !topMenuButton.visible
```

  That option removes them from the AT tree rather than making them reachable,
  and is listed only for completeness.

## Cross-workstream gate note

`tests/test_nd041_native_settings_controls_wiring.py` hashes every byte from
`visible: opened` to EOF in the two panels, so its
`RENDERED_VISUAL_SHA256` pin also covers accessibility-only lines. The new
pins after this change are:

- `SettingsPanel.qml`: `e5520ba7705c453014148cc98d36f3a71e725f65f68150b644adca6d2dc2c1c5`
- `QuickControlsOverlay.qml`: `19349a4fdd952bc9a83d24ea644e5ea84dbd512ad9f2be1f76074c67dddcda0c`

The complementary byte-level projection gate
(`tests/test_classic_status_a11y.py::test_visual_inputs_are_byte_frozen`)
strips `Accessible.*` lines and **passes**, proving that rendered text,
geometry, colours, fonts, ordering and assets are unchanged. Re-pinning the
ND-041 constant belongs to that test's owner (`tests/**` is outside this
change's ownership).
