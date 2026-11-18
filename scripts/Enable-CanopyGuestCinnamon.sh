#!/usr/bin/env bash
# Opt-in dedicated VirtualBox Mint guest ONLY. Does not reboot automatically.
set -Eeuo pipefail
if [[ "${1:-}" != "--enable" ]]; then
    echo "DRY-RUN. Pass --enable only inside the isolated Canopy Mint VM." >&2
    exit 0
fi
if [[ "$(id -un)" != "canopy-test" || "$EUID" == 0 ]]; then
    echo "Must run as dedicated unprivileged canopy-test account" >&2
    exit 2
fi
if ! grep -Eq '^ID=linuxmint$' /etc/os-release; then
    echo "Linux Mint guest required" >&2
    exit 2
fi
if [[ ! -r /sys/class/dmi/id/product_name ]] ||
   ! grep -qi 'virtualbox' /sys/class/dmi/id/product_name; then
    echo "Refuse to alter login configuration outside a VirtualBox VM" >&2
    exit 2
fi
if [[ ! -f /usr/share/xsessions/cinnamon.desktop ]]; then
    echo "Cinnamon X11 session unavailable" >&2
    exit 2
fi
if [[ -e /etc/lightdm/lightdm.conf.d/70-canopy-testlab.conf ]]; then
    echo "Autologin configuration already exists; no overwrite" >&2
    exit 2
fi
sudo -v
sudo install -d -m 755 /etc/lightdm/lightdm.conf.d
printf '%s\n' \
    '[Seat:*]' \
    'autologin-user=canopy-test' \
    'autologin-user-timeout=0' \
    'user-session=cinnamon' | sudo tee /etc/lightdm/lightdm.conf.d/70-canopy-testlab.conf >/dev/null
sudo chmod 644 /etc/lightdm/lightdm.conf.d/70-canopy-testlab.conf
echo "Dedicated Cinnamon test autologin configured; effect on next guest login only."
