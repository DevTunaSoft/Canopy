
P=$(pgrep -x plasmashell | head -1)
echo "NATIVE_ENV_SOURCE_PID=$P"
while IFS= read -r line; do
  case "$line" in
    DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_SESSION_TYPE=*|XDG_CURRENT_DESKTOP=*|XDG_RUNTIME_DIR=*) export "$line" ;;
  esac
done < <(tr '\0' '\n' < /proc/$P/environ)
echo "NATIVE_ENV_IMPORTED DISPLAY=$DISPLAY XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP XDG_SESSION_TYPE=$XDG_SESSION_TYPE"

echo "$ clean prior harness/app instances"
pkill -f 'build/native-task-harness' 2>/dev/null || true
pkill -x konsole 2>/dev/null || true
S=$(loginctl list-sessions --no-legend | grep seat0 | awk '{print $1}' | head -1)
echo "SEAT_SESSION=$S"
sudo -n loginctl unlock-session "$S" 2>&1 || true
sleep 1
echo "LOCKED_HINT=$(loginctl show-session "$S" | sed -n 's/^LockedHint=//p')"
echo "$ ps"
ps -eo pid,ppid,cmd | grep -E 'kwin_x11|plasmashell|sddm' | grep -v grep
echo "$ wmctrl"
wmctrl -lp
