#!/bin/bash
# Guest-side, read-only M3 native window-management facility probe.
# Stock Plasma session only: no compositor/service start, no VM/session change,
# no persistent setting, no desktop creation, no window launch or activation.
set +e
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
XAUTH=$(systemctl --user show-environment | sed -n 's/^XAUTHORITY=//p')
export DISPLAY=:0 XAUTHORITY="$XAUTH"

echo "=== UTC ==="; date -u
echo "=== SESSION ==="
pgrep -a -u canopy -f 'startplasma-x11|kwin_x11|plasmashell' | grep -v pgrep
echo "=== COMPOSITOR COUNT ==="
printf 'kwin_x11=%s plasmashell=%s\n' "$(pgrep -c -x kwin_x11)" "$(pgrep -c -x plasmashell)"
echo "=== KWIN BUS OWNER ==="
busctl --user status org.kde.KWin 2>&1 | head -8
echo "=== KWIN INTROSPECT ==="
timeout 10 busctl --user introspect org.kde.KWin /KWin 2>&1 | grep -E '^\.(currentDesktop|setCurrentDesktop|nextDesktop|previousDesktop)'
echo "=== FREEDESKTOP BUS NAME ==="
timeout 10 busctl --user list --no-pager 2>&1 | grep -w org.kde.KWin | head -1
echo "=== CURRENT DESKTOP ==="
timeout 10 busctl --user call org.kde.KWin /KWin org.kde.KWin currentDesktop 2>&1
echo "=== SET SAME DESKTOP (1) ==="
timeout 10 busctl --user call org.kde.KWin /KWin org.kde.KWin setCurrentDesktop i 1 2>&1
echo "=== CURRENT DESKTOP AFTER ==="
timeout 10 busctl --user call org.kde.KWin /KWin org.kde.KWin currentDesktop 2>&1
echo "=== EWMH ROOT READ (bounded) ==="
timeout 8 xprop -root _NET_CURRENT_DESKTOP _NET_ACTIVE_WINDOW _NET_DESKTOP_NAMES 2>&1
echo "EWMH_RC=$?"
echo "=== X CLIENT LIVENESS (bounded) ==="
timeout 8 wmctrl -l 2>&1
echo "WMCTRL_RC=$?"
echo "=== X BLOCKER PROCESSES ==="
ps -eo pid,ppid,stat,etime,args | grep -E 'xdotool (key|mousemove)' | grep -v grep | head -6
echo "=== COMPOSITOR COUNT AFTER ==="
printf 'kwin_x11=%s plasmashell=%s\n' "$(pgrep -c -x kwin_x11)" "$(pgrep -c -x plasmashell)"
echo "=== DONE ==="
