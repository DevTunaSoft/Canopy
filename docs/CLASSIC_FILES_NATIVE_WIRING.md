# Classic Files — native browse/open wiring (ND-040)

Scope: compiled Classic prototype only. Owned files are
`prototype/classic/FileModel.cpp`, `prototype/classic/FileModel.h`,
`prototype/classic/FolderTile.qml`, the Files source-contract tests in `tests/`,
and this note. `PreviewWindow.qml`, `main.cpp`, `SystemAppLauncher.*`,
`CMakeLists.txt`, artwork, wallpaper and menu-bar files were read as contracts
but not modified.

## What is wired

- **Bounded listing.** `FileModel` performs one synchronous, non-recursive
  `QDirIterator` pass on state change and stops at `kMaxEntries = 500`. There
  are no timers, workers, network calls or background refreshes.
- **Home containment.** Every candidate is canonicalised before it is
  accepted; a path must be the home root or under the home prefix. Symlink
  escapes and sibling-prefix paths are refused with a fixed reason string.
- **Parent / back / forward.** `navigate()`, `goUp()`, `goBack()` and
  `goForward()` share one canonical gate. Back and forward stacks are capped
  at `kMaxHistory = 64` entries; a new destination or an Up navigation clears
  the redo branch. A forward target that disappeared since the Back step is
  refused with `forward target unavailable` and the stack is cleared.
- **Safe native open.** The model exposes only the exact, case-sensitive
  `Files` dock label. `PreviewWindow.qml` (read-only here) passes that label to
  the existing host `SystemAppLauncher` GIO bridge; no path, URL, argv or
  caller-supplied text reaches the bridge, and failure is reported as refusal.
- **Pure-contract alignment.** The compiled model mirrors the merged
  `file_manager_intent`, `working_directory_policy` and `files_intent_preview`
  contracts: canonical containment before admission, bounded output, fixed
  refusal reasons, no path in a denial record and no process launch in QML.
- **Tile honesty.** `FolderTile.qml` keeps the approved folder artwork and all
  geometry/colours byte-identical; only comments and the accessible
  description changed, removing the false `no disk access` claim.

## Verification actually run

- `python3 -m unittest tests.test_classic_files_forward_navigation
  tests.test_classic_files_contract_alignment tests.test_classic_files_browser
  tests.test_classic_files_file_manager_launch
  tests.test_c100_apps_files_intent_preview
  tests.test_c100_apps_file_manager_intent
  tests.test_c100_apps_working_directory_policy` — **87 tests OK** at the
  feature head (baseline before the change: 75 OK; RED first: 6 expected
  failures for the missing forward contract, then 1 for the stale-redo
  refresh).
- `python3 tools/check_foundation.py` — **PASS**.
- Local UCRT64 CMake/Ninja configure + build of `prototype/classic` —
  **PASS**, `canopy-classic-spike.exe` linked. GIO dev headers are absent on
  this host, so the build used the existing disabled-launch fallback; this is
  a toolchain fact, not a native launch test.
- Scratch compiled harness (not committed) exercising the real `FileModel`
  with two temporary directories under home — **32/32 checks PASS**, including
  forward after Back, redo invalidation on a new branch, stale redo refusal
  with a `navigationChanged` refresh, outside-home refusal with a fixed
  path-free reason, exact-label validation, and the 64-entry history cap.

Labels: source tests and the scratch harness are `SYNTHETIC`; the local Qt
build is a real compile on Windows UCRT64 with GIO disabled. Full suite,
Mint VM and real screen-reader behaviour are `NOT_RUN` for this bounded task
because QA owns those serialized gates. Resource impact: bounded history and
bounded listing add no timers or background wakeups; incremental RAM is
capped by `kMaxHistory` and `kMaxEntries`. No stability, accessibility,
security or approved-visual trade-off was made for a minor gain.

## Remaining owner-gated work

- A visible Forward button would require editing `PreviewWindow.qml`, which is
  outside this task's ownership and inside the frozen visual contract; the
  model exposes the property and method for a separately approved UI change.
- Native file-manager action in Mint needs an observed native transcript;
  guest SSH/credentials and visual sign-off remain owner-controlled.
