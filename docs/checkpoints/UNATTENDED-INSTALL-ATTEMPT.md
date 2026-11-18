# Experimental dedicated Mint VM unattended install attempt

`scripts/start_mint_unattended.py` can **initiate** a VirtualBox unattended install on the dedicated, powered-off `Canopy-Test-Mint` VM, with explicit authorization, matching VM UUID, local ISO SHA-256 verified against independently authenticated expected digest, protected password file and successfully completed VirtualBox `--dry-run`. It then asks VBoxManage to start the guest installation headlessly. Success from the command means only the **request was accepted**, not that Linux Mint booted or installed correctly.

```powershell
py -3 -m scripts.start_mint_unattended --vboxmanage "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" --iso "C:\CanopyLab\linuxmint.iso" --password-file "C:\CanopyLab\secrets\password.txt" --iso-sha256 <authenticated-digest> --vm-uuid <dedicated-vm-uuid> --authorize-disposable-install
```

**Important:** This command modifies/installs onto the test VM virtual disk. Run it only after explicit one-time authorization to install into a disposable empty VM. Do not use on a personal VM or on host drives. Password files are never passed by command-line value, but are managed by the host owner. No automatic credential creation/recovery, first boot monitoring or native Mint Ubiquity template validation exists. On unsupported Mint ISOs, the dry-run fails closed and no install is attempted. Even if accepted, VBox may fail later in the installer: this must be detected by separate host/guest probes and never labeled PASS until verified.

Oracle VBox CLI docs: https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/vboxmanage.html. Mint signed ISO verification: https://linuxmint-installation-guide.readthedocs.io/en/latest/verify.html. CI uses mock VBox outputs, **no actual Mint VM installation tested**.
