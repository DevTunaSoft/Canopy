#!/bin/bash
# Real Plasma (KWin X11) capture of the native-branch Classic dock fix.
# Runs on the Canopy-Test-Plasma6 guest; writes only the evidence directory.
set -uo pipefail
ROOT=/home/canopy/native_dock_geometry_20261127
EV=$ROOT/evidence
mkdir -p "$EV/screenshots" "$EV/per_size" "$EV/logs"
LOG=$EV/logs/capture.log; RES=$EV/logs/results.txt
: > "$LOG"; : > "$RES"
ts(){ date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log(){ printf '%s %s\n' "$(ts)" "$*" >> "$LOG"; }
result(){ printf 'CHECK|%s|%s|%s\n' "$1" "$2" "$3" >> "$RES"; log "RESULT $1=$2 :: $3"; }
BIN=$ROOT/build/canopy-classic-spike
ART=$ROOT/src/prototype/classic/assets/approved
KWPID=$(pgrep -x kwin_x11 | head -1)
XAUTH="$(tr '\0' '\n' < /proc/$KWPID/environ | sed -n 's/^XAUTHORITY=//p')"
export DISPLAY=:0 XAUTHORITY="$XAUTH" XDG_RUNTIME_DIR=/run/user/1000 XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=KDE
log "ENV kwinpid=$KWPID exe=$(readlink -f /proc/$KWPID/exe)"
echo "KWIN $(pgrep -a kwin_x11)" | tee -a "$LOG"
echo "PLASMA $(pgrep -a plasmashell)" | tee -a "$LOG"
sha256sum "$BIN" > "$EV/logs/binary_sha256.txt"
cat "$EV/logs/binary_sha256.txt"
sha256sum "$ART/manifest.json" > "$EV/logs/approved_manifest_sha256.txt"
cat "$EV/logs/approved_manifest_sha256.txt"

set_mode(){
  local w=$1 h=$2 d=$3 name="${w}x${h}"
  local mode="$name"
  if ! xrandr --current | grep -qE "^[[:space:]]+${w}x${h}[[:space:]]"; then
    local mline; mline=$(cvt "$w" "$h" | grep Modeline | sed 's/^Modeline //' | tr -d '"')
    xrandr --newmode $mline >> "$LOG" 2>&1
    xrandr --addmode VGA-1 "${name}_60.00" >> "$LOG" 2>&1
    mode="${name}_60.00"
  fi
  xrandr --output VGA-1 --mode "$mode" >> "$LOG" 2>&1
  sleep 3
  xrandr --current > "$d/xrandr.txt" 2>&1
  if grep -q "VGA-1 connected primary ${w}x${h}+0+0" "$d/xrandr.txt"; then
    result "display_size_$name" PASS "$(grep -m1 'VGA-1 connected' "$d/xrandr.txt")"
  else
    xrandr --output VGA-1 --mode "$mode" >> "$LOG" 2>&1; sleep 3
    xrandr --current > "$d/xrandr.txt" 2>&1
    if grep -q "VGA-1 connected primary ${w}x${h}+0+0" "$d/xrandr.txt"; then
      result "display_size_$name" PASS "$(grep -m1 'VGA-1 connected' "$d/xrandr.txt")"
    else
      result "display_size_$name" FAIL "$(grep -m1 'VGA-1 connected' "$d/xrandr.txt")"
    fi
  fi
}

cleanup(){
  if [ -f "$EV/current.pid" ]; then
    old=$(cat "$EV/current.pid")
    if [ -r "/proc/$old/exe" ] && [ "$(readlink -f "/proc/$old/exe")" = "$(readlink -f "$BIN")" ]; then
      kill "$old" 2>/dev/null || true; sleep 2
    fi
  fi
}

run_size(){
  local w=$1 h=$2 name="${w}x${h}" d="$EV/per_size/${w}x${h}"
  mkdir -p "$d"; cleanup; set_mode "$w" "$h" "$d"
  nohup "$BIN" --approved-art-dir "$ART" >"$d/classic.log" 2>&1 < /dev/null &
  local pid=$!; echo "$pid" > "$EV/current.pid"; echo "$pid" > "$d/classic.pid"
  sleep 9
  if ! kill -0 "$pid" 2>/dev/null; then result "launch_$name" FAIL "pid exited"; return 0; fi
  printf 'PID=%s\nEXE=%s\n' "$pid" "$(readlink -f /proc/$pid/exe)" > "$d/identity.txt"
  local wid; wid=$(wmctrl -lp | awk -v p="$pid" '$3==p {print $1; exit}')
  echo "$wid" > "$d/window_id.txt"
  if [ -n "$wid" ] && [ "$(readlink -f /proc/$pid/exe)" = "$(readlink -f "$BIN")" ]; then
    result "launch_$name" PASS "pid=$pid wid=$wid"
  else
    result "launch_$name" FAIL "pid=$pid wid=${wid:-NONE}"
    return 0
  fi
  wmctrl -lpG | grep -i 'Canopy Classic' > "$d/wmctrl.txt" 2>&1 || true
  xdotool getwindowgeometry --shell "$wid" > "$d/window_geometry.txt" 2>&1
  scrot -o "$EV/screenshots/screen_$name.png" >> "$LOG" 2>&1
  sha256sum "$EV/screenshots/screen_$name.png" > "$d/screen_sha256.txt"
  result "screenshot_$name" PASS "$(cat "$d/screen_sha256.txt")"
}

run_size 1920 1080
run_size 1200 750
run_size 760 500
cleanup
echo "== results =="; cat "$RES"
echo "== files =="; ls -l "$EV/screenshots"
