# Mint OS unattended installation attempt — 2026-11-18

`scripts/Install-CanopyMintOS.ps1` is an **opt-in** VirtualBox unattended installer attempt for the dedicated `Canopy-Test-Mint` VM only. It validates a locally supplied ISO against a separately authenticated SHA-256, requires a local password file, verifies the VM is powered off, and performs a VirtualBox `unattended install --dry-run` first. Actual configuration only occurs with `-Install`. The script intentionally does not print passwords or automatically start a VM.

After the VM hardware has been created with `New-CanopyMintVM.ps1`, on a Windows host with VirtualBox installed:
```powershell
.\scripts\Install-CanopyMintOS.ps1 -IsoPath C:\path\to\linuxmint.iso -IsoSha256 <verified-64-hex-sha> -PasswordFile C:\private\mint-password.txt
# Only after reviewing the dry-run and accepting possible unsupported Mint behavior:
.\scripts\Install-CanopyMintOS.ps1 -IsoPath C:\path\to\linuxmint.iso -IsoSha256 <verified-64-hex-sha> -PasswordFile C:\private\mint-password.txt -Install
```

**This does not establish that VirtualBox supports unattended installation of the chosen Linux Mint release.** A dry-run can pass while real Mint installation fails. The user password file must be protected with Windows ACLs, must not be committed to Git, and should be removed securely when no longer needed. Do not run this against a personal VM or other Linux host. No automated guest OS install, login, first-boot verification, snapshot creation, SSH host-key trust, or unattended GUI testing has been demonstrated. Windows CI checks only the synthetic command shape.
