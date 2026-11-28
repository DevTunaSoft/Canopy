
P=$(pgrep -x plasmashell | head -1)
echo "NATIVE_ENV_SOURCE_PID=$P"
while IFS= read -r line; do
  case "$line" in
    DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_SESSION_TYPE=*|XDG_CURRENT_DESKTOP=*|XDG_RUNTIME_DIR=*) export "$line" ;;
  esac
done < <(tr '\0' '\n' < /proc/$P/environ)
echo "NATIVE_ENV_IMPORTED DISPLAY=$DISPLAY XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP XDG_SESSION_TYPE=$XDG_SESSION_TYPE"

cd /home/canopy/canopy_native_tasksmodel_m2
scrot -o evidence_activated.png
python3 -c 'import struct;d=open("evidence_activated.png","rb").read(24);print("PNG_DIMS",struct.unpack(">II",d[16:24]))'
sha256sum evidence_activated.png
