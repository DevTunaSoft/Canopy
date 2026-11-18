# Mint VM one-time guest setup track — 2026-11-18

`scripts/setup-mint-guest.sh` sets up the guest testing account with packages used by existing test suites, GTK3/X11 automation, and key-only SSH. Run **inside a freshly installed, disposable Linux Mint Cinnamon VM**, as the separately created `canopy-test` account with sudo permission. Provide a locally verified, dedicated ed25519 public key: `bash scripts/setup-mint-guest.sh --public-key-file /path/to/id_ed25519.pub`.

This requires an initial trusted way to copy files to the VM, create the restricted account, and authorize `sudo`. No passwordless sudo is granted. Root SSH and password SSH are disabled by dedicated sshd drop-in (only for the dedicated test VM). Do not run on existing production/personal Mint systems because its SSH configuration and `AllowUsers` rule are intentionally restrictive.

**Important:** This branch does not automate installation of the Linux Mint operating system, login to a Cinnamon graphical session, trusted key exchange, startup of a persistent test agent, or any host communication by itself. Real Mint package names and LightDM graphical test accessibility must be verified on target VM before claiming the one-click environment is operational. `sshd -t` validates configuration before enabling it. VM is not yet available.

Host SSH transport (separate branch) must pin the real guest fingerprint. Never use shell one-liners that download and execute unknown code. Before unattended graphical tests, choose an explicit kiosk-like isolated login strategy and verify screen/focus permissions.
