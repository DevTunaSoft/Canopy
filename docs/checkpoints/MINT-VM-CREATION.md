# Windows VirtualBox Mint VM creation track — 2026-11-18

`scripts/New-CanopyMintVM.ps1` creates the **virtual hardware only**. It accepts a locally acquired official Linux Mint Cinnamon ISO and its **independently authenticated** SHA-256, verifies the ISO hash, refuses existing VM names/disks, and prepares a dedicated 4 GiB RAM, 2 vCPU, 40 GiB VDI VirtualBox guest. NAT is enabled, SSH is forwarded only from localhost TCP 2222, clipboard/drag-and-drop are disabled. No shared folders and no public inbound network port.

```powershell
powershell.exe -NoProfile -File .\scripts\New-CanopyMintVM.ps1 -IsoPath C:\path\to\linuxmint.iso -IsoSha256 <official-signed-ISO-hash>
```

This first runs DRY RUN. Add `-Create` to execute explicitly. **The script does not install Linux Mint, start the VM, install packages, or set up the guest SSH key.** Official VirtualBox `unattended install` support for arbitrary Mint ISOs is not guaranteed; an untested unattended install must not be advertised as working. Integrating a verified Mint preseed/custom-ISO or tested VBox unattended path remains critical. Source for ISO signature verification: https://linuxmint-installation-guide.readthedocs.io/en/latest/verify.html. The checksum must be authenticated, not blindly copied from the same untrusted mirror as the ISO.

Before release, test exact VBoxManage commands on the target Windows/VirtualBox version and verify a safe rollback if partial VM creation fails. GitHub Windows synthetic self-tests do not count as real VM testing.
