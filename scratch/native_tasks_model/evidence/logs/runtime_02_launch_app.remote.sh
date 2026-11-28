
P=$(pgrep -x plasmashell | head -1)
echo "NATIVE_ENV_SOURCE_PID=$P"
while IFS= read -r line; do
  case "$line" in
    DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_SESSION_TYPE=*|XDG_CURRENT_DESKTOP=*|XDG_RUNTIME_DIR=*) export "$line" ;;
  esac
done < <(tr '\0' '\n' < /proc/$P/environ)
echo "NATIVE_ENV_IMPORTED DISPLAY=$DISPLAY XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP XDG_SESSION_TYPE=$XDG_SESSION_TYPE"

echo "$ gio launch /usr/share/applications/org.kde.konsole.desktop"
nohup gio launch /usr/share/applications/org.kde.konsole.desktop </dev/null >/dev/null 2>&1 &
echo "GIO_LAUNCH_SPAWNED=$!"
sleep 3
echo "--- konsole after launch"; pgrep -a konsole || true
