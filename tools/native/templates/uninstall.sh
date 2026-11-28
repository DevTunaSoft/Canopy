#!/usr/bin/env bash
# Remove the Canopy Classic baseline applet and restore stock Plasma config,
# but only when the config is byte-identical to the snapshot taken at install.
# Usage: uninstall.sh <state-dir>
set -euo pipefail
STATE="${1:-}"
if [ -z "$STATE" ] || [ ! -d "$STATE" ]; then
    echo "UNINSTALL_FAIL: usage uninstall.sh <state-dir>" >&2
    exit 2
fi
CONFIG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
BACKUP="$STATE/backup/plasma-org.kde.plasma.desktop-appletsrc"
INSTALLED="$STATE/installed-config.sha256"

if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -Fxq "org.kde.plasma.canopyclassic"; then
    kpackagetool6 --type Plasma/Applet --remove org.kde.plasma.canopyclassic
fi
if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -Fxq "org.kde.plasma.canopyclassic"; then
    echo "UNINSTALL_FAIL: package still listed after removal" >&2
    exit 3
fi

if [ -f "$CONFIG" ] && [ -f "$INSTALLED" ] && \
   [ "$(sha256sum "$CONFIG" | awk '{print $1}')" = "$(cat "$INSTALLED")" ]; then
    if [ -f "$BACKUP" ]; then
        cp -p "$BACKUP" "$CONFIG"
        echo "UNINSTALL_PASS: stock Plasma config restored byte-for-byte"
    else
        echo "UNINSTALL_PASS: no pre-existing config snapshot; config unchanged"
    fi
else
    if [ -f "$CONFIG" ]; then
        cp -p "$CONFIG" "$STATE/user-preserved/plasma-org.kde.plasma.desktop-appletsrc"
    fi
    echo "UNINSTALL_PASS_USER_CONFIG_PRESERVED: config differs from install snapshot; not overwritten"
fi
sha256sum "$CONFIG" 2>/dev/null | awk '{print $1}' > "$STATE/uninstalled-config.sha256" || true
