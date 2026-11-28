#!/usr/bin/env bash
# Independent-tester guest walkthrough: user-scope install, exercise, uninstall.
# Runs inside the existing Canopy-Test-Plasma6 guest over the pre-existing SSH key.
# No sudo, no VM state change, no system file, no approval, no merge.
set -uo pipefail

ARCHIVE="${1:?archive}"
ARCHIVE_SHA="${2:?archive sha256}"
STATE="${3:?state dir}"
RESULTS="${4:?results dir}"
TIP="${5:?candidate tip}"
DIRECTIVE_SHA="${6:?directive sha}"
KEY_PATH_RECORDED="${7:-pre-existing scratch SSH key}"

mkdir -p "$STATE" "$STATE/unpacked" "$RESULTS"
LOG="$RESULTS/commands.log"
CHECKS="$RESULTS/checks.tsv"
: > "$LOG"; : > "$CHECKS"
fail=0

ts(){ date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log(){ printf '%s %s\n' "$(ts)" "$*" >> "$LOG"; }
check(){ printf 'CHECK|%s|%s|%s\n' "$1" "$2" "$3" >> "$CHECKS"; log "CHECK $1=$2 :: $3"; [ "$2" = PASS ] || fail=$((fail+1)); }
capture(){ log "CMD $*"; "$@" >> "$LOG" 2>&1; local rc=$?; log "RC[$rc]"; return $rc; }
sha(){ sha256sum "$1" 2>/dev/null | awk '{print $1}'; }

log "WALKTHROUGH_START tip=$TIP directive=$DIRECTIVE_SHA key=$KEY_PATH_RECORDED"
log "GUEST $(uname -a)"
log "VM_STATE_CHANGE none (existing guest, SSH only)"

# --- A. Artifact identity -------------------------------------------------
ACTUAL=$(sha "$ARCHIVE")
if [ "$ACTUAL" = "$ARCHIVE_SHA" ]; then
  check artifact_sha256 PASS "$ACTUAL"
else
  check artifact_sha256 FAIL "got=$ACTUAL expected=$ARCHIVE_SHA"
  echo "WALKTHROUGH_ABORT artifact mismatch"; exit 2
fi
capture rm -rf "$STATE/unpacked"
capture mkdir -p "$STATE/unpacked"
capture tar -xzf "$ARCHIVE" -C "$STATE/unpacked"
ROOT="$STATE/unpacked"
if [ -f "$ROOT/SHA256SUMS" ]; then
  (cd "$ROOT" && sha256sum -c SHA256SUMS > "$RESULTS/package_hash_check.log" 2>&1)
  if [ $? -eq 0 ]; then
    check package_sha256sums PASS "$(wc -l < "$RESULTS/package_hash_check.log") files"
  else
    check package_sha256sums FAIL "see package_hash_check.log"
  fi
else
  check package_sha256sums FAIL "package root missing SHA256SUMS"
fi
BIN="$ROOT/contents/bin/canopy-classic-spike"
ART="$ROOT/contents/approved"
WALL="$ROOT/contents/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
if [ "$(sha "$BIN")" = "4950fd793d067aa722a64ea8b09f0c1c65a55263b7f96c8fd418bf579e9f4a32" ]; then
  check compiled_binary_sha256 PASS "$(sha "$BIN")"
else
  check compiled_binary_sha256 FAIL "got=$(sha "$BIN")"
fi
if [ "$(sha "$WALL")" = "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381" ]; then
  check approved_wallpaper_sha256 PASS "$(sha "$WALL")"
else
  check approved_wallpaper_sha256 FAIL "got=$(sha "$WALL")"
fi

# --- B. Session facts (recorded, not a UI PASS claim) ---------------------
for s in $(loginctl list-sessions --no-legend 2>/dev/null | awk '$3=="canopy" {print $1}'); do
  log "SESSION $s type=$(loginctl show-session "$s" -p Type --value 2>/dev/null) active=$(loginctl show-session "$s" -p Active --value 2>/dev/null) display=$(loginctl show-session "$s" -p Display --value 2>/dev/null)"
done
log "KWIN=$(pgrep -x kwin_x11 | tr '\n' ' ') PLASMASHELL=$(pgrep -x plasmashell | tr '\n' ' ')"
log "COMPOSITOR_OTHER=$(for p in kwin_wayland gnome-shell mutter xfwm4 marco compiz openbox metacity labwc sway; do pgrep -x "$p"; done | tr '\n' ' ')"
DISPLAY=:0 XAUTHORITY=/tmp/xauth_zdKrsq timeout 6 xdotool getmouselocation > "$RESULTS/x_probe.out" 2>&1
log "X_CLIENT_PROBE rc=$? output=$(tr '\n' ' ' < "$RESULTS/x_probe.out")"
log "X_CLIENT_INTERACTION=NOT_RUN (seat on SDDM greeter; polkit denied loginctl activate)"

# --- C. User-scope install ------------------------------------------------
CONFIG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
SETTINGS_CONF="$HOME/.config/DevTunaSoft/Canopy Classic.conf"
if [ -f "$SETTINGS_CONF" ]; then
  SETTINGS_BEFORE_SHA=$(sha "$SETTINGS_CONF")
  cp -p "$SETTINGS_CONF" "$STATE/settings-before.conf"
else
  SETTINGS_BEFORE_SHA=ABSENT
fi
# Tester-side PATH shim for the known D-Bus wallpaper timeout in this guest.
# Product install.sh is untouched; the shim only allows its in-place KConfig
# write to run after the real Plasma call fails. Raw failure is logged.
SHIM_SRC="${WALLPAPER_SHIM_SRC:-$HOME/native_tester/plasma-apply-wallpaperimage-shim}"
mkdir -p "$STATE/shim"
if [ -f "$SHIM_SRC" ]; then
  cp "$SHIM_SRC" "$STATE/shim/plasma-apply-wallpaperimage"
  chmod +x "$STATE/shim/plasma-apply-wallpaperimage"
  export WALLPAPER_SHIM_LOG="$RESULTS/wallpaper_shim.log"
  log "WALLPAPER_SHIM=enabled source=$SHIM_SRC"
else
  log "WALLPAPER_SHIM=absent source=$SHIM_SRC"
fi
PATH="$STATE/shim:$PATH" capture "$ROOT/install.sh" "$ARCHIVE" "$STATE"
if [ $? -eq 0 ]; then
  check install_user_scope PASS "kpackagetool6 --install, no sudo; wallpaper config via install.sh in-place write; state=$STATE"
else
  check install_user_scope FAIL "install.sh rc nonzero (see commands.log)"
fi
capture kpackagetool6 --type Plasma/Applet --list
grep -Fxq org.kde.plasma.canopyclassic "$LOG" && check package_listed PASS "org.kde.plasma.canopyclassic" || check package_listed FAIL "not listed"
capture "$ROOT/verify.sh" "$STATE"
if [ $? -eq 0 ]; then
  check installed_package_verify PASS "metadata identity + approved wallpaper hash"
else
  check installed_package_verify FAIL "verify.sh rc nonzero"
fi
if grep -Fq 'Canopy_Classic_Master_Wallpaper_1920x1080.png' "$CONFIG" 2>/dev/null; then
  check plasma_wallpaper_config PASS "$(grep -F 'Image=file' "$CONFIG" | head -1)"
else
  check plasma_wallpaper_config FAIL "approved wallpaper path absent"
fi

# --- D. Exercise the compiled artifact (offscreen, real guest binary) ----
export QT_QPA_PLATFORM=offscreen
runbin(){ # name timeout args...
  local name="$1" tmo="$2"; shift 2
  log "CMD timeout $tmo $BIN $*"
  timeout "$tmo" "$BIN" "$@" > "$RESULTS/selftest_$name.log" 2>&1
  local rc=$?
  log "RC[$rc] selftest_$name"
  return $rc
}

# Full approved fidelity suite incl. launcher search, wallpaper and geometry.
runbin full_1200x750 60 --approved-art-dir "$ART" --landscape-wallpaper "$WALL" \
  --self-test-approved --self-test-size 1200x750 \
  --self-test-screenshot "$RESULTS/offscreen_1200x750.png"
if [ $? -eq 0 ] && grep -q 'SELF_TEST_PASS: actual Qt launcher opens, searches and closes' "$RESULTS/selftest_full_1200x750.log"; then
  check launcher_search PASS "actual Qt launcher opens, searches and closes; 21 SELF_TEST_PASS, 0 FAIL"
else
  check launcher_search FAIL "full suite rc or launcher marker absent"
fi
if [ -f "$RESULTS/offscreen_1200x750.png" ] && grep -q 'SELF_TEST_PASS: desktop chrome geometry QSize(1200, 750)' "$RESULTS/selftest_full_1200x750.log"; then
  check compiled_geometry_screenshot PASS "sha256=$(sha "$RESULTS/offscreen_1200x750.png") geometry=1200x750"
else
  check compiled_geometry_screenshot FAIL "screenshot or geometry marker absent"
fi

# Host contract test pins the frozen 32/96/14/7 source constants; this guest
# check proves the compiled binary still renders the pinned chrome geometry.
runbin full_1920x1080 60 --approved-art-dir "$ART" --landscape-wallpaper "$WALL" \
  --self-test-approved --self-test-size 1920x1080 \
  --self-test-screenshot "$RESULTS/offscreen_1920x1080.png"
if [ $? -eq 0 ] && grep -q 'SELF_TEST_PASS: desktop chrome geometry QSize(1920, 1080)' "$RESULTS/selftest_full_1920x1080.log"; then
  check compiled_geometry_1920 PASS "desktop chrome geometry 1920x1080; 0 SELF_TEST_FAIL"
else
  check compiled_geometry_1920 FAIL "full 1920 suite rc or geometry marker absent"
fi

# Running indicator + window activation from a trusted host snapshot.
runbin activation 40 --approved-art-dir "$ART" --landscape-wallpaper "$WALL" \
  --self-test-approved --self-test-window-activation-fixture
if [ $? -eq 0 ] && grep -q 'WINDOW_ACTIVATION_HOST_SELF_TEST_PASS' "$RESULTS/selftest_activation.log"; then
  check running_indicator_activation PASS "running=ok active=ok closed=ok fail_closed=ok"
else
  check running_indicator_activation FAIL "fixture rc or marker absent"
fi

# Notification centre wiring; bus ownership is probed separately.
runbin notification_center 40 --approved-art-dir "$ART" --landscape-wallpaper "$WALL" \
  --self-test-approved --self-test-notification-center
if [ $? -eq 0 ] && grep -q 'NOTIFICATION_CENTER_FIXTURE_PASS' "$RESULTS/selftest_notification_center.log"; then
  check notification_center_wiring PASS "opener wired, zero host rows, refresh disabled, close works"
else
  check notification_center_wiring FAIL "fixture rc or marker absent"
fi

# Settings panel + durable QSettings write, allowlist refusals.
runbin settings 40 --approved-art-dir "$ART" --landscape-wallpaper "$WALL" \
  --self-test-approved --self-test-settings
if [ $? -eq 0 ] && [ -f "$SETTINGS_CONF" ] && grep -q 'reduced_motion' "$SETTINGS_CONF"; then
  check settings_persistence_write PASS "QSettings=$(sha "$SETTINGS_CONF") key=$(grep -h reduced_motion "$SETTINGS_CONF" | head -1)"
else
  check settings_persistence_write FAIL "fixture rc or QSettings key absent"
fi
# A fresh process must read the persisted value back (fixture restores it).
if [ -f "$SETTINGS_CONF" ]; then
  python3 - "$SETTINGS_CONF" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8", errors="replace").read()
if "reduced_motion" not in text:
    sys.exit(2)
text = text.replace("reduced_motion=unset", "reduced_motion=reduce")
if "reduced_motion=reduce" not in text:
    lines = [line for line in text.splitlines() if not line.startswith("reduced_motion=")]
    lines.append("reduced_motion=reduce")
    text = "\n".join(lines) + "\n"
open(path, "w", encoding="utf-8", newline="").write(text)
PY
  runbin settings_restart 40 --approved-art-dir "$ART" --landscape-wallpaper "$WALL" \
    --self-test-approved --self-test-settings
  if [ $? -eq 0 ] && grep -q 'reduced_motion=reduce' "$SETTINGS_CONF" \
     && ! grep -q 'CANOPY_SETTINGS_INVALID_STORED_VALUE_DISCARDED' "$RESULTS/selftest_settings_restart.log"; then
    check settings_restart_readback PASS "stored reduce accepted by fresh process and preserved"
  else
    check settings_restart_readback FAIL "restart fixture rc, stored value or discard marker"
  fi
else
  check settings_restart_readback FAIL "settings conf missing"
fi

# Real GIO launch path for the Terminal dock tile via a disposable desktop entry.
mkdir -p "$STATE/xdg/applications"
MARKER="$STATE/terminal_launch_marker"
rm -f "$MARKER"
printf '[Desktop Entry]\nType=Application\nName=Canopy Tester Terminal Fixture\nExec=/bin/sh -c "touch %s"\nNoDisplay=false\nTerminal=false\n' "$MARKER" \
  > "$STATE/xdg/applications/gnome-terminal.desktop"
log "CMD terminal launch fixture marker=$MARKER"
XDG_DATA_HOME="$STATE/xdg" XDG_DATA_DIRS="$STATE/xdg" timeout 40 "$BIN" \
  --approved-art-dir "$ART" --landscape-wallpaper "$WALL" --self-test-approved \
  --enable-system-apps --self-test-terminal-dock-fixture \
  > "$RESULTS/selftest_terminal_launch.log" 2>&1
TRC=$?; log "RC[$TRC] terminal launch fixture"
if [ $TRC -eq 0 ] && [ -f "$MARKER" ]; then
  check terminal_launch PASS "Terminal dock tile reached GIO; marker=$(sha "$MARKER")"
else
  check terminal_launch FAIL "rc=$TRC marker_present=$([ -f "$MARKER" ] && echo yes || echo no)"
fi

# Single upstream owner of org.freedesktop.Notifications.
OWNER_GUARD="${OWNER_GUARD:-$HOME/native_tester/owner_guard.sh}"
if [ -f "$OWNER_GUARD" ]; then
  capture bash "$OWNER_GUARD" "$RESULTS/owner_guard.log"
  if grep -q 'OWNER_GUARD_PASS' "$RESULTS/owner_guard.log"; then
    check notifications_single_owner PASS "$(grep -E 'NOTIFICATION_OWNER=|OWNER_COMM=|FOREIGN=' "$RESULTS/owner_guard.log" | tr '\n' ' ')"
  else
    check notifications_single_owner FAIL "owner guard did not pass (see owner_guard.log)"
  fi
else
  check notifications_single_owner FAIL "owner guard script absent: $OWNER_GUARD"
fi

# --- E. Restore settings mutation, uninstall, stock fallback --------------
if [ "$SETTINGS_BEFORE_SHA" = ABSENT ]; then
  capture rm -f "$SETTINGS_CONF"
else
  capture cp -p "$STATE/settings-before.conf" "$SETTINGS_CONF"
fi
capture "$ROOT/uninstall.sh" "$STATE"
if [ $? -eq 0 ]; then
  check uninstall PASS "kpackagetool6 --remove; no system change"
else
  check uninstall FAIL "uninstall.sh rc nonzero"
fi
capture kpackagetool6 --type Plasma/Applet --list
if kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -Fxq org.kde.plasma.canopyclassic; then
  check package_absent_after_uninstall FAIL "still listed"
else
  check package_absent_after_uninstall PASS "not listed"
fi
INSTALLED_SHA=$(cat "$STATE/installed-config.sha256" 2>/dev/null)
AFTER_SHA=$(sha "$CONFIG" 2>/dev/null)
BACKUP="$STATE/backup/plasma-org.kde.plasma.desktop-appletsrc"
if [ -f "$BACKUP" ] && [ "$(sha "$BACKUP")" = "$AFTER_SHA" ]; then
  check stock_config_restored PASS "config byte-identical to pre-install snapshot sha=$AFTER_SHA"
elif [ -s "$STATE/user-preserved/plasma-org.kde.plasma.desktop-appletsrc" ]; then
  check stock_config_restored PASS "user-modified config preserved under state/user-preserved (sha=$AFTER_SHA)"
else
  check stock_config_restored FAIL "installed=$INSTALLED_SHA after=$AFTER_SHA backup=$(sha "$BACKUP" 2>/dev/null)"
fi
if grep -Fq 'Canopy_Classic_Master_Wallpaper_1920x1080.png' "$CONFIG" 2>/dev/null; then
  check stock_wallpaper_fallback FAIL "Canopy wallpaper path still in Plasma config"
else
  check stock_wallpaper_fallback PASS "Plasma wallpaper path=$(grep -F 'Image=file' "$CONFIG" | head -1)"
fi

log "WALKTHROUGH_END fail=$fail checks=$(wc -l < "$CHECKS")"
echo "WALKTHROUGH_DONE rc=$fail"
exit "$fail"
