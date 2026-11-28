# Out-of-ownership a11y root-cause fix (M3/M5)

- Branch: `product/a11y-rootcause-20261128`, base `ec910d7a7275296ecbc8b5e5c459d356205165d1`
  (`integration/canopy-plasma6-20261127`), directive Rev3 SHA `1fba4b1e`.
- Owned paths only: `prototype/classic/PreviewWindow.qml`, `prototype/classic/Main.qml`,
  `docs/NATIVE_A11Y_ROOTCAUSE_FIX.md`, `scratch/a11y_rootcause/**`.
- **DRAFT only. No merge, no approval, no self-approval, no base-branch change.**
  Final visual acceptance remains `AWAITING_OWNER_FINAL_VISUAL_ACCEPTANCE`.

## Root causes inherited from PR #752

PR #752 (`395cced2`) proved the remaining PR #740 defects originate in files
that were outside its ownership grant; its prepared hunks were explicitly
**NOT APPLIED**. They are applied here by the now-free owners:

### D1 — unnamed secondary file-detail labels (7 / 7 / 6)

`prototype/classic/PreviewWindow.qml`, delegate of `objectName: "canopyFileRow"`.
For folder rows `isDir === true`, the secondary `Label` binds
`text: isDir ? "" : size + " B"` and therefore exposed an empty AT name.
Five accessibility-only lines were added:

- primary label: `Accessible.name: name` and
  `Accessible.description: isDir ? "Folder name" : "File name"`;
- secondary label: `Accessible.ignored: isDir`,
  `Accessible.name: isDir ? "" : size + " B"` and
  `Accessible.description: "File size in bytes"`.

Folder rows no longer publish an unnamed label; file rows keep an explicit
name and description. This follows the non-visual option recommended in
`scratch/native_a11y_qml/OUT_OF_OWNERSHIP_ROOT_CAUSES.md` on PR #752 rather
than inventing a synthetic "Folder — no size" name.

### D2 — Window/Help named but unreachable at 760×500

`prototype/classic/Main.qml`, `topMenuButton` delegate of the six-menu
`Repeater`. The base rule
`visible: !root.compactLayout || (modelData !== "Window" && modelData !== "Help")`
kept those two buttons in the AT tree with null extents at compact width.
It is replaced by `visible: true` with an explanatory comment. All six
approved menus now have real extents and retain their existing
`Accessible.name: modelData + " menu"` and
`Accessible.description: "Open the " + modelData + " menu"`.

The existing `Item { Layout.fillWidth: true }` spacer absorbs the two
buttons: at 760 px the margins (16+16), 30 px launcher, four short menu
labels, two restored labels, 10 px spacing and clock still fit well inside
the bar. No width, height, anchor, spacing, font, colour, opacity, z, image,
timer, animation, menu action or shortcut line was added or changed. The
approved 32/96/14/7 geometry line, `Theme.qml` and `prototype/classic/assets/**`
are byte-identical to the base.

PR #752's non-visual `Alt+W` / `Alt+H` shortcuts in `ShellMenuBar.qml` are
left untouched: this branch adds no `Shortcut`, so no duplicate accelerator
is created when both changes coexist. PR #660's launcher-item names and
Files-list focus names touch different hunks of these two files and are
unchanged here. At base, 19 `Accessible.*` lines existed in the two owned
QML files; at this head there are 24 and no base accessibility line was
removed.

## Static / targeted verification (all actually run)

| Check | Result | Evidence |
| --- | --- | --- |
| Owned static source gate, 15 checks | **PASS 15/15**, rc=0 | `scratch/a11y_rootcause/verify_rootcause_a11y.py`, `verify_rootcause_a11y.json` |
| Focused QML/source contracts (status a11y, shell menus, dock lock, top bar, ND-041, Qt source, classic source) | **Ran 65 tests ... OK**, rc=0 | `targeted_tests.log` |
| `test_c100_accessibility_*` pattern gates | **Ran 132 tests ... OK**, rc=0 | `accessibility_pattern_tests.log` |
| Extended wiring/keyboard gates | **Ran 73 tests ... OK**, rc=0 | `extended_wiring_tests.log` |
| Foundation check | **PASS** | `foundation_check.log` |
| Visual-lock check | `problems=0`, `AWAITING_CHATGPT_VISUAL_APPROVAL` | `visual_lock_check.log` |
| AT-SPI in real Plasma at this head | **`BLOCKED`** | `atspi_blocker_probe.py`, `atspi_blocker_probe.json` |
| Screen reader / Orca announcements | **`NOT_RUN`** | same probe |
| Real Mint acceptance / final owner visual approval | **`NOT_RUN` / `AWAITING_OWNER_FINAL_VISUAL_ACCEPTANCE`** | no guest session was entered |

The static gate includes two byte-level projections: the
`PreviewWindow.qml` non-accessibility projection is identical to the base pin
`741091d6324db4193b2c4300c438a502631ed550604c271405e9d2e56d2eaeec` (the same
definition used by `tests/test_classic_status_a11y.py`), and every
`Main.qml` rendered binding except the deliberate visibility rule is
byte-identical. The dock tail, including the final root brace, is
byte-frozen. No Qt compile and no CI result is claimed locally.

## Exact AT-SPI blocker (fresh read-only probe)

The VirtualBox guest `Canopy-Test-Plasma6` is `running` with NAT SSH forward
127.0.0.1:2223, but the guest-property list exposes no guest-execution
channel, `~/.ssh` contains only `known_hosts` files (no private key), and this
Windows host has no `DISPLAY`, no `QT_QPA_PLATFORM` and no `pyatspi`. No guest
login was supplied, no credential was guessed, and **no VM state, guest
command, snapshot, display or screen reader was changed**
(`vm_mutations=0`, `guest_commands=0`, `credentials_used=0`). Prior PR #740
and #752 AT-SPI evidence predates this head and is not relabelled as proof of
it. To close the blocker: supply an authorized guest lease/login, rebuild
this exact head in Plasma with `QT_ACCESSIBILITY=1`, and query AT-SPI at
1920×1080, 1200×750 and 760×500 including actual Window/Help activation.

## Resource / evidence note

**SYNTHETIC**: Python-only text reads, bounded counters and git blob
comparisons in the static gate; no service, thread, timer or persistent
state. **NOT_RUN**: real guest RSS/CPU, native AT-SPI, screen-reader
announcements and final visual acceptance. Screen-reader behaviour is
explicitly `NOT_RUN`; no stability, security, accessibility or approved
visual quality was traded for a resource gain.

## Evidence integrity

Git-blob SHA-256 (LF-normalized bytes at this head):

- `prototype/classic/PreviewWindow.qml`: `baeb7dacf63a135938bc09151c7dbdc63dea2f3e0bd3a947d0835bd46a9d17ce`
- `prototype/classic/Main.qml`: `05ec83ed87c44103f0ffa6ab990a5aea02bebff84927cd03656ee39ccdaf40f6`

Per-file digests for all evidence artifacts are in
`scratch/a11y_rootcause/SHA256SUMS.txt`; verify with `sha256sum -c` from the
`scratch/a11y_rootcause` directory. An inventory of all 273 open PRs and the
REST file check for the only other PR touching these QML paths (#660) are
retained in `open_prs.json` and `pr660_diff.txt`.
