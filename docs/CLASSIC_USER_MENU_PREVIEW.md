# Canopy Classic — reversible user-level application menu (prototype)

**Scope:** A Linux Mint or other freedesktop-compatible desktop session can
show Canopy Classic as an **application** in its existing application menu.
This does **not** install a new desktop session, replace Cinnamon, change the
display manager, switch compositors, start services or run as root.

The source lives in tools/register_classic_preview.py. It uses Python's
standard library and writes only:
- $XDG_DATA_HOME/applications/org.canopy.ClassicPreview.desktop
- $XDG_DATA_HOME/canopy/classic-preview/ownership.json

The ownership marker is a SHA-256 digest of the exact installed desktop entry.
The tool refuses to overwrite another entry, refuses symlinks at managed
locations, and refuses to uninstall if either the marker or desktop entry was
modified. It deliberately retains folders and any unrelated user files.

## Example on an existing Linux Mint desktop

Build or obtain the **separately verified Qt6 Classic prototype** from draft
PR #100 (or its eventual accepted successor); record its exact build SHA.
Do not use an unapproved mockup as a functional release.

Run as your ordinary desktop user, NEVER with sudo:

    python3 tools/register_classic_preview.py status
    python3 tools/register_classic_preview.py install --binary /absolute/path/to/canopy-classic-spike

Optional approved artwork (paths must be absolute and safe):

    python3 tools/register_classic_preview.py install --binary /absolute/path/to/canopy-classic-spike --approved-art-dir "/absolute/path/to/exact approved art" --landscape-wallpaper "/absolute/path/to/approved alpine.png" --terminal-refinement "/absolute/path/to/refined-terminal-v3.png"

The optional --enable-system-apps flag, available on the separately tested
native launcher draft (#102), requests real installed apps through GIO.
It is off by default and has not been verified with real Nemo/Firefox inside
Linux Mint. Do not pass it to a binary that does not support it.

Uninstall:

    python3 tools/register_classic_preview.py uninstall
    python3 tools/register_classic_preview.py status

There is no automatic update or network download. If the user changes the
desktop entry, the tool refuses to remove it; the user should inspect and
reconcile their changes rather than have automation delete unknown content.

## What CI validates

The workflow classic-user-menu.yml runs Python negative-control tests and
uses desktop-file-validate against a real registered desktop entry in a
**disposable Ubuntu runner XDG_DATA_HOME**, then removes it. It also
deliberately changes a desktop entry and verifies uninstall refuses to
delete that modified user file. No real application is launched.

**NOT VERIFIED:** Real Linux Mint panel/menu refresh, keyboard accessibility,
the desktop environment's launch behavior, a real Canopy Qt installation,
update rollback after a crash, rootless packaging beyond a menu entry,
actual desktop-session selection, or any new UI visual acceptance. These
require separate in-guest testing. A desktop entry is not a complete shell
installer, and the register/unregister pair is not crash-atomic across its
two separate files.

Potential administrative/recovery concern: if a power loss occurs between
writing a desktop entry and its ownership marker, status reports
MODIFIED_OR_UNMANAGED and refuses destructive cleanup. That is intentional
fail-closed behavior, not automatic crash recovery.

## Actual compiled Qt launch proof in the Classic Qt draft

The separate `.github/workflows/classic-qt.yml` job, on the active
**draft** Classic Qt stack, extends the baseline synthetic-menu checks:

1. Builds the actual C++/QML Canopy Classic executable in Ubuntu CI.
2. Creates an isolated temporary XDG application-menu folder.
3. Uses this **same existing** `register_classic_preview.py` to register
   the compiled binary directly, verifying its executable SHA-256.
4. Validates the real freedesktop entry and runs `gio launch` under Xvfb.
5. Requires a *new current-user process matching the original executable
   inode* and a visible X11 window with Canopy's actual application title.
6. Stops only the newly observed exact executable process, unregisters
   only the exact-owned temporary desktop entry, and removes the isolated
   test folder. It never modifies the user's actual application menu.

The runner is `python3 -m tools.classic_menu_runtime_smoke --binary
/absolute/path/to/canopy-classic-spike --expected-binary-sha256
<actual-64-hex-sha256>`, normally inside a fresh disposable Xvfb display.
Its ten negative-control tests include symlinked binaries, source-hash
mismatch, non-executables, missing DISPLAY, failed X11 window evidence,
and lack of root privileges. The runner uses no shell, no root and
no background service.

**Interpretation:** A passing Ubuntu/Xvfb GIO→Qt launch and window test
means the binary is capable of starting as an ordinary menu application.
It does **not** mean the installer is a full shell/session integration,
or that Linux Mint Cinnamon displays the menu item, launches it correctly,
or supports full focus/window management. These remain separately required
in a real guest. The app icon, wallpaper and launcher art are still subject
to user visual approval.
