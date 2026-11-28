#!/usr/bin/env bash
# Install the pinned Canopy Classic development baseline at Plasma user scope.
# Usage: install.sh <package-archive.tar.gz> <state-dir>
# Never uses sudo and never changes system files or approved asset bytes.
set -euo pipefail

ARCHIVE="${1:-}"
STATE="${2:-}"
if [ -z "$ARCHIVE" ] || [ -z "$STATE" ] || [ ! -f "$ARCHIVE" ]; then
    echo "INSTALL_FAIL: usage install.sh <archive> <state-dir>" >&2
    exit 2
fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HERE"
WALLPAPER="$ROOT/contents/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
EXPECTED_WALLPAPER="8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381"
CONFIG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
mkdir -p "$STATE/backup" "$STATE/user-preserved"

cd "$ROOT"
sha256sum -c SHA256SUMS > "$STATE/install_hash_check.log"
ACTUAL="$(sha256sum "$WALLPAPER" | awk '{print $1}')"
if [ "$ACTUAL" != "$EXPECTED_WALLPAPER" ]; then
    echo "INSTALL_FAIL: approved wallpaper hash mismatch: $ACTUAL" >&2
    exit 3
fi

if [ -f "$CONFIG" ]; then
    cp -p "$CONFIG" "$STATE/backup/plasma-org.kde.plasma.desktop-appletsrc"
    printf '%s  %s\n' "$(sha256sum "$CONFIG" | awk '{print $1}')" \
        "$(stat -c '%a' "$CONFIG")" > "$STATE/backup/config.meta"
else
    : > "$STATE/backup/config.meta"
fi

if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -Fxq "org.kde.plasma.canopyclassic"; then
    kpackagetool6 --type Plasma/Applet --upgrade "$ARCHIVE"
else
    kpackagetool6 --type Plasma/Applet --install "$ARCHIVE"
fi
kpackagetool6 --type Plasma/Applet --show org.kde.plasma.canopyclassic > "$STATE/installed_metadata.json"

plasma-apply-wallpaperimage "$WALLPAPER"
# plasma-apply-wallpaperimage reports success but this guest sometimes delays
# or skips the on-disk KConfig sync. Persist the exact path in the existing
# image-wallpaper group in place; every other byte of the user config is kept.
python3 - "$CONFIG" "$WALLPAPER" <<'PY'
import re, sys
config, wallpaper = sys.argv[1], sys.argv[2]
with open(config, encoding="utf-8") as stream:
    text = stream.read()
pattern = re.compile(
    r'(?ms)^(\[Containments\]\[\d+\]\[Wallpaper\]\[org\.kde\.image\]\[General\][ \t]*\n)'
    r'(.*?)(?=^\[Containments\]|\Z)')
match = pattern.search(text)
if match is None:
    sys.exit("INSTALL_FAIL: no Plasma image wallpaper config group")
body = re.sub(r'(?m)^Image=.*$', 'Image=file://' + wallpaper, match.group(2), count=1)
if body == match.group(2) and 'Image=file://' + wallpaper not in text:
    sys.exit("INSTALL_FAIL: could not set Image key in wallpaper group")
with open(config, "w", encoding="utf-8", newline="") as stream:
    stream.write(text[:match.start()] + match.group(1) + body + text[match.end():])
PY
for _i in $(seq 1 20); do
  grep -Fq "Canopy_Classic_Master_Wallpaper_1920x1080.png" "$CONFIG" 2>/dev/null && break
  sleep 1
done
if ! grep -Fq "Canopy_Classic_Master_Wallpaper_1920x1080.png" "$CONFIG" 2>/dev/null; then
    echo "INSTALL_FAIL: wallpaper path not present in Plasma config" >&2
    exit 4
fi
sha256sum "$CONFIG" | awk '{print $1}' > "$STATE/installed-config.sha256"
echo "INSTALL_PASS: user-scope KPackage installed; approved wallpaper applied"
