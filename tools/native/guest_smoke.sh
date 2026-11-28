#!/usr/bin/env bash
# Guest-side smoke test for the Canopy Classic native Plasma 6 development baseline.
# Executed by tools/native/smoke_test.py over SSH in the existing reference guest.
# Required env: ARCHIVE ARCHIVE_SHA STATE RESULTS SOURCE_SHA BINARY_SHA WALLPAPER_SHA.
# No sudo, no credentials, no VM state change, no repo mutation, no release claim.
set -uo pipefail
mkdir -p "$STATE" "$RESULTS" "$STATE/unpacked"
LOG="$RESULTS/commands.log"
CHECKS="$RESULTS/checks.txt"
: > "$LOG"; : > "$CHECKS"
rm -f "$RESULTS/binary_selftest.log"
ts(){ date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log(){ printf '%s %s\n' "$(ts)" "$*" >> "$LOG"; }
check(){ printf 'CHECK|%s|%s|%s\n' "$1" "$2" "$3" >> "$CHECKS"; log "CHECK $1=$2 :: $3"; [ "$2" = PASS ] || fail=$((fail+1)); }
capture(){ log "CMD $*"; "$@" >> "$LOG" 2>&1; local rc=$?; log "RC[$rc]"; return $rc; }
sha(){ sha256sum "$1" 2>/dev/null | awk '{print $1}'; }

fail=0
check_requested(){ [ "$2" = PASS ] || fail=$((fail+1)); }

REPO_SHA="$(sha "$ARCHIVE")"
if [ "$REPO_SHA" = "$ARCHIVE_SHA" ]; then
  check archive_sha256 PASS "$REPO_SHA"
else
  check archive_sha256 FAIL "got=$REPO_SHA expected=$ARCHIVE_SHA"; exit 2
fi

# --- Real Plasma user session (not Xvfb, not a standalone Qt window) ---
SID=""
for s in $(loginctl list-sessions --no-legend 2>/dev/null | awk '$3=="canopy" {print $1}'); do
  st="$(loginctl show-session "$s" -p Type --value 2>/dev/null)"
  sc="$(loginctl show-session "$s" -p Class --value 2>/dev/null)"
  sa="$(loginctl show-session "$s" -p Active --value 2>/dev/null)"
  if [ "$st" = x11 ] && [ "$sc" = user ] && [ "$sa" = yes ]; then SID="$s"; break; fi
done
if [ -n "$SID" ]; then
  capture loginctl show-session "$SID" -p Type -p Class -p Display -p Active -p State -p Remote -p Name
  STYPE="$(loginctl show-session "$SID" -p Type --value 2>/dev/null)"
  SACTIVE="$(loginctl show-session "$SID" -p Active --value 2>/dev/null)"
  SCLASS="$(loginctl show-session "$SID" -p Class --value 2>/dev/null)"
  SDISP="$(loginctl show-session "$SID" -p Display --value 2>/dev/null)"
  if [ "$STYPE" = x11 ] && [ "$SACTIVE" = yes ] && [ "$SCLASS" = user ]; then
    check real_plasma_user_session PASS "session=$SID type=$STYPE class=$SCLASS active=$SACTIVE"
  else
    check real_plasma_user_session FAIL "session=$SID type=$STYPE class=$SCLASS active=$SACTIVE"
  fi
else
  check real_plasma_user_session FAIL "no active canopy user session at smoke start"
fi

KWPIDS="$(pgrep -x kwin_x11 | tr '\n' ' ')"
if [ "$(pgrep -xc kwin_x11)" -eq 1 ] && [ "$(pgrep -x plasmashell | wc -l)" -ge 1 ]; then
  check single_compositor_and_shell PASS "kwin_x11=[$KWPIDS] plasmashell=$(pgrep -c plasmashell)"
else
  check single_compositor_and_shell FAIL "kwin_x11=[$KWPIDS] plasmashell=$(pgrep -c plasmashell || true)"
fi
OTHER="$(for p in kwin_wayland gnome-shell mutter xfwm4 marco compiz openbox metacity labwc sway; do pgrep -x "$p"; done | tr '\n' ' ')"
if [ -z "$OTHER" ]; then
  check no_second_compositor PASS "none"
else
  check no_second_compositor FAIL "$OTHER"
fi
KWPID="$(pgrep -x kwin_x11 | head -1)"
XAUTH="$(tr '\0' '\n' < "/proc/$KWPID/environ" 2>/dev/null | sed -n 's/^XAUTHORITY=//p' | head -1)"
export DISPLAY=:0 XAUTHORITY="$XAUTH" XDG_RUNTIME_DIR=/run/user/1000
export XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=KDE
log "ENV DISPLAY=$DISPLAY XAUTHORITY=$XAUTH XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"

# --- Unpack and gate exact artifact bytes ---
rm -rf "$STATE/unpacked"
mkdir -p "$STATE/unpacked"
capture tar -xzf "$ARCHIVE" -C "$STATE/unpacked"
ROOT="$STATE/unpacked"
if [ -f "$ROOT/SHA256SUMS" ]; then
  check package_layout PASS "$ROOT"
else
  check package_layout FAIL "unpacked package root missing SHA256SUMS"; exit 3
fi
(cd "$ROOT" && sha256sum -c SHA256SUMS > "$RESULTS/package_hash_check.log" 2>&1)
if [ $? -eq 0 ]; then
  check package_sha256sums PASS "$(wc -l < "$RESULTS/package_hash_check.log") files"
else
  check package_sha256sums FAIL "see package_hash_check.log"
fi
BIN="$ROOT/contents/bin/canopy-classic-spike"
WALL="$ROOT/contents/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
APPROVED="$ROOT/contents/approved"
if [ "$(sha "$BIN")" = "$BINARY_SHA" ]; then
  check binary_sha256 PASS "$BINARY_SHA"
else
  check binary_sha256 FAIL "got=$(sha "$BIN") expected=$BINARY_SHA"
fi
if [ "$(sha "$WALL")" = "$WALLPAPER_SHA" ]; then
  check approved_wallpaper_sha256 PASS "$WALLPAPER_SHA"
else
  check approved_wallpaper_sha256 FAIL "got=$(sha "$WALL") expected=$WALLPAPER_SHA"
fi
log "SOURCE_COMMIT=$SOURCE_SHA"

# --- Install at Plasma user scope and apply the exact approved wallpaper ---
capture "$ROOT/install.sh" "$ARCHIVE" "$STATE"
IRC=$?
if [ "$IRC" -eq 0 ]; then
  check install PASS "kpackagetool6 user scope; approved wallpaper applied"
else
  check install FAIL "install.sh rc=$IRC (see commands.log)"
fi
capture "$ROOT/verify.sh" "$STATE"
VRC=$?
if [ "$VRC" -eq 0 ]; then
  check installed_package_verify PASS "KPackage metadata and wallpaper hash"
else
  check installed_package_verify FAIL "verify.sh rc=$VRC"
fi
CONFIG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
if grep -Fq 'Canopy_Classic_Master_Wallpaper_1920x1080.png' "$CONFIG" 2>/dev/null; then
  check plasma_wallpaper_config PASS "$(grep -F 'Canopy_Classic_Master_Wallpaper_1920x1080.png' "$CONFIG" | head -1)"
else
  check plasma_wallpaper_config FAIL "approved wallpaper path absent from Plasma config"
fi

# --- Real compiled Classic binary inside the real Plasma X11 session ---
# The full --self-test-approved suite is a separate gate and is not used here:
# this smoke test proves install, wallpaper, launch and a live desktop window.
RUNLOG="$RESULTS/classic_runtime.log"
log "CMD $BIN --approved-art-dir $APPROVED --landscape-wallpaper $WALL"
"$BIN" --approved-art-dir "$APPROVED" --landscape-wallpaper "$WALL" > "$RUNLOG" 2>&1 &
BPID=$!
sleep 5
WINDOWS=""
for _w in $(seq 1 20); do
  kill -0 "$BPID" 2>/dev/null || break
  WINDOWS="$(xdotool search --pid "$BPID" 2>/dev/null | tr '\n' ' ')"
  [ -n "$WINDOWS" ] && break
  sleep 1
done
if kill -0 "$BPID" 2>/dev/null; then
  WMLINE="$(wmctrl -l 2>/dev/null | grep -i canopy | head -1)"
  if [ -n "$WINDOWS" ]; then
    check classic_window_live PASS "pid=$BPID xdotool_windows=[$WINDOWS] wmctrl=[$WMLINE]"
  else
    check classic_window_live FAIL "pid=$BPID alive but no X11 window; see classic_runtime.log"
  fi
else
  check classic_window_live FAIL "binary exited early; see classic_runtime.log"
fi
if grep -q CANOPY_APPROVED_ART_VERIFIED "$RUNLOG" && \
   grep -q CANOPY_LANDSCAPE_WALLPAPER_VERIFIED "$RUNLOG"; then
  check runtime_approved_art_and_wallpaper PASS "exact icons and landscape wallpaper verified at launch"
else
  check runtime_approved_art_and_wallpaper FAIL "launch verification markers absent"
fi
SHOT="$RESULTS/plasma_session_with_classic.png"
capture scrot -o "$SHOT"
if [ -f "$SHOT" ] && [ "$(stat -c %s "$SHOT")" -gt 10000 ]; then
  DIMS="$(python3 -c 'import struct,sys; d=open(sys.argv[1],"rb").read(24); print("%dx%d" % struct.unpack(">II", d[16:24]))' "$SHOT" 2>/dev/null)"
  check real_desktop_classic_screenshot PASS "sha256=$(sha "$SHOT") dimensions=$DIMS"
else
  check real_desktop_classic_screenshot FAIL "desktop capture missing or blank"
fi
if kill -0 "$BPID" 2>/dev/null; then
  kill "$BPID" 2>/dev/null
  wait "$BPID" 2>/dev/null
fi
if kill -0 "$BPID" 2>/dev/null; then
  check classic_process_terminated FAIL "pid=$BPID still alive"
else
  check classic_process_terminated PASS "pid=$BPID stopped"
fi

capture scrot -o "$RESULTS/plasma_session.png"
if [ -f "$RESULTS/plasma_session.png" ] && [ "$(stat -c %s "$RESULTS/plasma_session.png")" -gt 10000 ]; then
  check plasma_session_screenshot PASS "sha256=$(sha "$RESULTS/plasma_session.png")"
else
  check plasma_session_screenshot FAIL "real desktop screenshot missing or blank"
fi

# --- Restore stock Plasma state; never leave the baseline installed ---
capture "$ROOT/uninstall.sh" "$STATE"
URC=$?
if [ "$URC" -eq 0 ]; then
  check uninstall PASS "rc=0; config restored or user changes preserved"
else
  check uninstall FAIL "uninstall.sh rc=$URC"
fi
if ! kpackagetool6 --type Plasma/Applet --list 2>/dev/null | grep -Fxq org.kde.plasma.canopyclassic; then
  check baseline_absent_after_uninstall PASS "package not listed"
else
  check baseline_absent_after_uninstall FAIL "package still listed"
fi
(cd "$RESULTS" && sha256sum $(ls -1 | grep -v '^SHA256SUMS$' | sort) > SHA256SUMS 2>/dev/null)
printf 'SMOKE_GUEST_VERDICTTABLE %s\n' "$(grep -c '|PASS|' "$CHECKS") PASS / $(grep -c '|FAIL|' "$CHECKS" || true) FAIL"
if [ "$fail" -eq 0 ]; then
  echo "SMOKE_GUEST_PASS"
  exit 0
fi
echo "SMOKE_GUEST_FAIL ($fail failing checks)"
exit 1
