#!/bin/sh
# Read-only M3 native quick-controls probe. Delivered over SSH on stdin.
# Nothing is written in the guest. No toggle, elevation, activation or sysfs write.
set -u
run() {
  printf '$ %s\n' "$*"
  "$@" 2>&1
  printf '[exit=%s]\n' "$?"
}
section="${1:-all}"
printf 'M3_PROBE_SECTION=%s\n' "$section"
printf 'M3_PROBE_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

case "$section" in
  env)
    run printf 'SESSION_BUS=%s\n' "$DBUS_SESSION_BUS_ADDRESS"
    run printf 'XDG_RUNTIME_DIR=%s\n' "$XDG_RUNTIME_DIR"
    run pgrep -a -f 'org_kde_powerdevil|NetworkManager|systemd-logind|plasmashell|kwin_x11'
    run gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.ListNames
    ;;
  brightness)
    run gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.NameHasOwner org.kde.Solid.PowerManagement
    run gdbus call --session --dest org.kde.Solid.PowerManagement --object-path /org/kde/Solid/PowerManagement --method org.kde.Solid.PowerManagement.isActionSupported BrightnessControl
    run gdbus introspect --session --dest org.kde.Solid.PowerManagement --object-path /org/kde/Solid/PowerManagement/Actions/BrightnessControl
    run gdbus call --session --dest org.kde.Solid.PowerManagement --object-path /org/kde/Solid/PowerManagement --method org.freedesktop.DBus.Properties.GetAll org.kde.Solid.PowerManagement
    run gdbus call --session --dest org.kde.ScreenBrightness --object-path /org/kde/ScreenBrightness --method org.freedesktop.DBus.Properties.Get org.kde.ScreenBrightness DisplaysDBusNames
    run ls -la /sys/class/backlight/
    run find /sys/class/backlight -maxdepth 4 \( -name brightness -o -name max_brightness -o -name actual_brightness \) -print
    ;;
  network)
    run gdbus call --system --dest org.freedesktop.NetworkManager --object-path /org/freedesktop/NetworkManager --method org.freedesktop.NetworkManager.GetPermissions
    run gdbus call --system --dest org.freedesktop.NetworkManager --object-path /org/freedesktop/NetworkManager --method org.freedesktop.DBus.Properties.Get org.freedesktop.NetworkManager State
    run gdbus call --system --dest org.freedesktop.NetworkManager --object-path /org/freedesktop/NetworkManager --method org.freedesktop.DBus.Properties.Get org.freedesktop.NetworkManager Connectivity
    run gdbus call --system --dest org.freedesktop.NetworkManager --object-path /org/freedesktop/NetworkManager --method org.freedesktop.DBus.Properties.Get org.freedesktop.NetworkManager ConnectivityCheckAvailable
    run gdbus call --system --dest org.freedesktop.NetworkManager --object-path /org/freedesktop/NetworkManager --method org.freedesktop.DBus.Properties.Get org.freedesktop.NetworkManager ActiveConnections
    run gdbus call --system --dest org.freedesktop.NetworkManager --object-path /org/freedesktop/NetworkManager --method org.freedesktop.NetworkManager.CheckConnectivity
    run nmcli general status
    run nmcli device status
    ;;
  power)
    run gdbus call --system --dest org.freedesktop.login1 --object-path /org/freedesktop/login1 --method org.freedesktop.login1.Manager.CanSuspend
    run gdbus call --system --dest org.freedesktop.login1 --object-path /org/freedesktop/login1 --method org.freedesktop.login1.Manager.CanHibernate
    run gdbus call --system --dest org.freedesktop.login1 --object-path /org/freedesktop/login1 --method org.freedesktop.login1.Manager.CanPowerOff
    run gdbus call --system --dest org.freedesktop.login1 --object-path /org/freedesktop/login1 --method org.freedesktop.login1.Manager.ListJobs
    run gdbus call --session --dest org.freedesktop.UPower --object-path /org/freedesktop/UPower --method org.freedesktop.DBus.Properties.Get org.freedesktop.UPower OnBattery
    run loginctl show-session "$XDG_SESSION_ID" -p Type -p Service -p Remote -p Active
    ;;
  *)
    printf 'UNKNOWN_SECTION\n'
    exit 2
    ;;
esac
