#!/bin/bash
# Guest-side runtime driver: stock Plasma session, stock desktop entries only.
# No staged/duplicated service file, no XDG override, no package/setting change.
set +e
G=/home/canopy/native_terminal_launch_20261127
BIN=$G/build/canopy-classic-spike
APPROVED=$G/src/prototype/classic/assets/approved
RT=$G/runtime
mkdir -p "$RT"
XAUTH=$(systemctl --user show-environment | sed -n 's/^XAUTHORITY=//p')
export DISPLAY=:0 XAUTHORITY="$XAUTH" XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
echo "=== UTC ==="; date -u
echo "=== PLASMA SESSION ==="
pgrep -a -u canopy -f 'startplasma-x11|kwin_x11|plasmashell' | grep -v pgrep
echo "=== ENV ==="
printf 'DISPLAY=%s XAUTHORITY=%s XDG_DATA_DIRS=%s\n' "$DISPLAY" "$XAUTHORITY" "$XDG_DATA_DIRS"
echo "=== GIO LOOKUP (stock XDG data dirs) ==="
python3 "$RT/gio_lookup.py"
echo "=== KONSOLE BEFORE ==="; pgrep -a konsole || echo NONE
echo "=== DBUS BEFORE ==="
busctl --user list --no-pager | grep -iE 'konsole|terminal' || echo NO_TERMINAL_BUS_NAME
echo "=== X WINDOWS BEFORE ==="
xdotool search --name 'Konsole' 2>/dev/null || echo NONE
echo "=== TERMINAL DOCK LAUNCH FIXTURE ==="
"$BIN" --enable-system-apps --self-test-approved --approved-art-dir "$APPROVED" \
    --self-test-terminal-dock-fixture 2>&1
echo "LAUNCH_RC=$?"
sleep 4
echo "=== KONSOLE AFTER ==="; pgrep -a konsole || echo NONE
echo "=== PROCESS TREE ==="
for p in $(pgrep konsole); do
    ps -o pid,ppid,pgid,sid,stat,etime,args -p "$p"
    pstree -aps "$p" 2>/dev/null
done
echo "=== DBUS AFTER ==="
busctl --user list --no-pager | grep -iE 'konsole|terminal' || echo NO_TERMINAL_BUS_NAME
echo "=== X WINDOWS AFTER ==="
wmctrl -l | grep -iE 'konsole|canopy classic' || echo NONE
for w in $(wmctrl -l | grep -i konsole | awk '{print $1}'); do
    xdotool getwindowgeometry "$w" 2>/dev/null
    wmctrl -i -a "$w" 2>/dev/null
    sleep 1
    scrot -u -o "$RT/konsole_window.png" 2>&1
done
wmctrl -a 'Canopy Classic' 2>/dev/null
echo "=== ROOT SCREENSHOT ==="
scrot -o "$RT/root_after.png" 2>&1
ls -l "$RT/root_after.png" 2>&1
echo "=== RESTORE ==="
for p in $(pgrep konsole); do
    kill "$p" 2>/dev/null && echo "KILLED $p"
done
sleep 2
pgrep -a konsole || echo NO_KONSOLE
echo "=== GUEST STOCK ENTRY UNCHANGED ==="
sha256sum /usr/share/applications/org.kde.konsole.desktop
echo "=== DONE ==="
