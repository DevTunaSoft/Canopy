#!/usr/bin/env bash
# One-time guest bootstrap ONLY inside disposable Linux Mint 22 Cinnamon VM.
# Needs sudo authorization once; no auto-login or passwordless sudo.
set -Eeuo pipefail
umask 077
if [[ "${EUID}" -eq 0 ]]; then
  echo "Run as the ordinary Mint user with sudo rights, not as root" >&2; exit 2
fi
if ! grep -Eq '^ID=linuxmint$' /etc/os-release; then
  echo "This script only supports a verified Linux Mint VM" >&2; exit 2
fi
if [[ "${1:-}" != "--public-key-file" || ! -f "${2:-}" ]]; then
  echo "Usage: ./scripts/setup-mint-guest.sh --public-key-file /path/to/verified/id_ed25519.pub" >&2
  exit 2
fi
PUBKEY="$2"
if [[ -L "$PUBKEY" ]] || [[ "$(wc -l < "$PUBKEY")" -ne 1 ]] ||
   ! grep -Eq '^ssh-ed25519 [A-Za-z0-9+/=]+( .*)?$' "$PUBKEY"; then
  echo "Expected one verified, regular ed25519 public key" >&2; exit 2
fi
if [[ "$(id -un)" != "canopy-test" ]]; then
  echo "Run as the dedicated canopy-test account (no other users changed)" >&2
  exit 2
fi
sudo -v
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  openssh-server python3 python3-gi gir1.2-gtk-3.0 xvfb xauth \
  git xdotool wmctrl x11-utils
HOME_DIR="$(getent passwd canopy-test | cut -d: -f6)"
if [[ "$HOME_DIR" != "/home/canopy-test" ]]; then
  echo "Unexpected test account home; refusing SSH configuration" >&2; exit 3
fi
install -d -m 700 "$HOME_DIR/.ssh"
install -m 600 "$PUBKEY" "$HOME_DIR/.ssh/authorized_keys"
SSH_DROPIN="/etc/ssh/sshd_config.d/60-canopy-testlab.conf"
printf '%s\n' \
  'PasswordAuthentication no' \
  'KbdInteractiveAuthentication no' \
  'PermitRootLogin no' \
  'AllowUsers canopy-test' | sudo tee "$SSH_DROPIN" >/dev/null
sudo chmod 644 "$SSH_DROPIN"
sudo /usr/sbin/sshd -t
sudo systemctl enable --now ssh
install -d -m 700 "$HOME_DIR/canopy-runs"
echo "Guest dependencies and keyed SSH configured; Cinnamon session autologin remains OFF."
echo "Host must independently pin SSH host fingerprint before first connection."
