#!/usr/bin/env bash
# Read-only verification of an installed Canopy Classic baseline package.
# Usage: verify.sh <state-dir>
set -euo pipefail
STATE="${1:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HERE"
CONFIG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"

cd "$ROOT"
sha256sum -c SHA256SUMS
SHOW="$(kpackagetool6 --type Plasma/Applet --show org.kde.plasma.canopyclassic)"
printf '%s\n' "$SHOW" > "$STATE/verify_show.txt"
printf '%s\n' "$SHOW" | grep -Eq 'Plugin[[:space:]]*: org\.kde\.plasma\.canopyclassic'
INSTALLED_PATH="$(printf '%s\n' "$SHOW" | sed -n 's/^[[:space:]]*Path[[:space:]]*: //p' | head -1)"
[ -n "$INSTALLED_PATH" ] && [ -f "$INSTALLED_PATH/metadata.json" ]
cp "$INSTALLED_PATH/metadata.json" "$STATE/verify_metadata.json"
python3 - "$STATE/verify_metadata.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["KPackageStructure"] == "Plasma/Applet"
assert data["X-Plasma-API-Minimum-Version"] == "6.0"
assert data["KPlugin"]["Id"] == "org.kde.plasma.canopyclassic"
print("METADATA_IDENTITY_OK")
PY
for _i in $(seq 1 20); do
  grep -Fq "Canopy_Classic_Master_Wallpaper_1920x1080.png" "$CONFIG" 2>/dev/null && break
  sleep 1
done
grep -Fq "Canopy_Classic_Master_Wallpaper_1920x1080.png" "$CONFIG"
[ "$(sha256sum "$ROOT/contents/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png" | awk '{print $1}')" = \
  "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381" ]
echo "VERIFY_PASS: package identity and approved wallpaper hash match"
