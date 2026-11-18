# VirtualBox unattended ISO capability preflight — 2026-11-18

The official VirtualBox CLI has `VBoxManage unattended install ... --dry-run` support. Whether this works with the current Linux Mint Cinnamon ISO is **not verified**; historically some Linux Mint Ubiquity ISOs do not support the same unattended template as Ubuntu. `scripts/probe_vbox_unattended.py` is a **non-destructive dry-run** for an already created, powered-off `Canopy-Test-Mint` VM. It checks the exact dedicated VM identity, local ISO and supplied protected password-file, runs a dry-run and emits an explicit capability result.

```powershell
py -3 -m scripts.probe_vbox_unattended --vboxmanage "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" --iso C:\CanopyLab\linuxmint.iso --password-file C:\CanopyLab\secrets\mint-password.txt
```

A passing dry-run is NOT a successful OS installation; this module never boots or changes the VM. The password file must be restricted to the Windows host user; this script checks size, not its Windows ACL. The eventual production installer must authenticate a signed ISO checksum, verify the guest's installer version, and perform a disposable-VM trial with actual boot/desktop/SSH evidence before shipping one-click unattended installation. If unsupported, implement a pinned, reviewed Mint 22.x Ubiquity preseed image builder in a separate trusted Linux build environment; do not silently run an unreviewed third-party script or ask the user to expose their Windows host.

Oracle VirtualBox reference: https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/vboxmanage.html.
