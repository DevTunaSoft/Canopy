# Independent host-controller track — 2026-11-18

`scripts/vbox_lab_controller.py` adds a restricted VirtualBox control-plane primitive intended to run on the **Windows host**, outside the future Linux Mint VM. It supports only `status`, `start`, and explicitly authorized `reset` for the exact VM name `Canopy-Test-Mint`. It verifies VM identity/UUID and state before/after operations, checks the exact `Canopy-Clean` snapshot before restore, never performs an implicit poweroff, and runs without guest credentials, shared folders or remote listeners.

Usage after the VM is created (from a trusted Windows Python installation):
```powershell
py -3 -m scripts.vbox_lab_controller status --vboxmanage "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
py -3 -m scripts.vbox_lab_controller start --vboxmanage "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
```

Reset is intentionally separate and destructive **only to the disposable VM**, and requires it to be powered off and a local `--allow-reset` authorization. This authorization will eventually be embedded in an explicitly approved local test-lab setup; do not use on a personal or unsnapshotted VM. Snapshot restore can erase guest changes, so retain all needed diagnostic artifacts externally before resetting. The host orchestration/scheduler, guest acknowledgments, and trusted evidence transfer are NOT IMPLEMENTED. No actual VirtualBox or Mint VM was accessed.

The precise VBoxManage command families are documented by Oracle: https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/vboxmanage.html . Tests use mocked VBoxManage responses. Risk: VBoxManage is a trusted local command line but is not itself an independent guest-health oracle. It cannot establish that Cinnamon logged in or that Canopy runs correctly.
