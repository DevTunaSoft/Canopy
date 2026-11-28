
P=$(pgrep -x plasmashell | head -1)
echo "NATIVE_ENV_SOURCE_PID=$P"
while IFS= read -r line; do
  case "$line" in
    DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_SESSION_TYPE=*|XDG_CURRENT_DESKTOP=*|XDG_RUNTIME_DIR=*) export "$line" ;;
  esac
done < <(tr '\0' '\n' < /proc/$P/environ)
echo "NATIVE_ENV_IMPORTED DISPLAY=$DISPLAY XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP XDG_SESSION_TYPE=$XDG_SESSION_TYPE"

cd /home/canopy/canopy_native_tasksmodel_m2
rm -f harness.log harness.pid
nohup env DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" \
  DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  XDG_SESSION_TYPE="$XDG_SESSION_TYPE" XDG_CURRENT_DESKTOP="$XDG_CURRENT_DESKTOP" \
  XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  ./build/native-task-harness --auto ./harness/NativeTaskHarness.qml \
  > harness.log 2>&1 &
echo "HARNESS_PID=$!" | tee harness.pid
