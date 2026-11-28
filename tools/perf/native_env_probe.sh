#!/usr/bin/env bash
# Guest-side read-only environment/background-services probe.
# ssh ... canopy@127.0.0.1 'bash -s' < tools/perf/native_env_probe.sh > raw/env_probe.txt
set -u
printf 'UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '$ hostname\n'; hostname
printf '$ uname -a\n'; uname -a
printf '$ cat /etc/os-release\n'; cat /etc/os-release
printf '$ lscpu\n'; lscpu | head -25
printf '$ dpkg-query plasma/kwin/qt6\n'
dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' 'plasma*' 'kwin*' 'qt6-*' 2>/dev/null | grep -E '^(plasma-shell|plasma-workspace|kwin-x11|qt6-base-dev|libqt6core6|libqt6quick6|qml6-module-qtquick) ' | head -20
printf '$ qmake6 -v\n'; qmake6 -v 2>&1 | head -5
printf '$ pkg-config Qt6Core Qt6Quick\n'; pkg-config --modversion Qt6Core Qt6Quick 2>&1 | head -5
printf '$ running system services\n'; systemctl list-units --type=service --state=running --no-pager --no-legend 2>&1 | head -60
printf '$ running user services\n'; DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user list-units --type=service --state=running --no-pager --no-legend 2>&1 | head -60
printf '$ canopy binary identity\n'
for b in /home/canopy/.local/bin/canopy-classic /home/canopy/native_build_baseline/out/build/canopy-classic-spike; do
  if [ -f "$b" ]; then stat -c '%n %s bytes mtime=%y' "$b"; sha256sum "$b"; fi
done
printf '$ canopy pids/cmdlines\n'; pgrep -a -f 'canopy-classic|native-task-harness' | head -20
printf '$ X session\n'; DISPLAY=:0 XAUTHORITY=/tmp/xauth_zdKrsq wmctrl -lpG 2>&1 | head -20
printf '$ xrandr\n'; DISPLAY=:0 XAUTHORITY=/tmp/xauth_zdKrsq xrandr --current 2>&1 | head -12
