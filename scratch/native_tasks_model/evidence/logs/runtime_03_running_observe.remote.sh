
P=$(pgrep -x plasmashell | head -1)
echo "NATIVE_ENV_SOURCE_PID=$P"
while IFS= read -r line; do
  case "$line" in
    DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_SESSION_TYPE=*|XDG_CURRENT_DESKTOP=*|XDG_RUNTIME_DIR=*) export "$line" ;;
  esac
done < <(tr '\0' '\n' < /proc/$P/environ)
echo "NATIVE_ENV_IMPORTED DISPLAY=$DISPLAY XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP XDG_SESSION_TYPE=$XDG_SESSION_TYPE"

cd /home/canopy/canopy_native_tasksmodel_m2
echo "--- windows"; wmctrl -lp
# Steal focus back to the harness before the upstream activation phase.
WID=$(wmctrl -lp | grep 'Canopy Classic native task dock' | tail -1 | awk '{print $1}')
echo "HARNESS_WID=$WID"
xdotool windowactivate --sync "$WID" 2>&1 || true
sleep 1
echo "--- konsole"; pgrep -a konsole || true
echo "--- active before activation"; xdotool getactivewindow getwindowname || true
echo "--- log tail"; tail -30 harness.log
