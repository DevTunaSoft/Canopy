
P=$(pgrep -x plasmashell | head -1)
echo "NATIVE_ENV_SOURCE_PID=$P"
while IFS= read -r line; do
  case "$line" in
    DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_SESSION_TYPE=*|XDG_CURRENT_DESKTOP=*|XDG_RUNTIME_DIR=*) export "$line" ;;
  esac
done < <(tr '\0' '\n' < /proc/$P/environ)
echo "NATIVE_ENV_IMPORTED DISPLAY=$DISPLAY XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP XDG_SESSION_TYPE=$XDG_SESSION_TYPE"

echo "--- before list"; kpackagetool6 --type Plasma/Applet --list | grep -i canopy || echo NO_CANOPY_APPLET
echo "--- config hashes"; sha256sum "$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc" "$HOME/.config/plasmashellrc" 2>&1
