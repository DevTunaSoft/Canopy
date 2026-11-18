# Canopy Mint VM — Windows operator quickstart

**Status:** Hardware provisioning and VirtualBox unattended installation are *experimental*. Do not run on an existing personal VM. These commands create a dedicated 40 GiB virtual disk and can modify VirtualBox's registered VM list. Nothing has yet been executed on the user's Windows machine.

## 1. Prerequisites

- Windows 11, VirtualBox installed from the official Oracle website, at least 8 GiB available RAM, 45 GiB free disk space, virtualization enabled.
- Download the current **Linux Mint Cinnamon** ISO from https://linuxmint.com/download.php and verify the SHA256 checksum and signed checksum file using https://linuxmint-installation-guide.readthedocs.io/en/latest/verify.html.
- Download/clone the **specific reviewed Canopy branch**, not an untrusted pull-request artifact. Open PowerShell in its repository root.

## 2. Inspect the host

```powershell
.\scripts\Test-CanopyHost.ps1
.\scripts\Install-Canopy-TestLab.ps1
```

Read the reported prerequisite status and local plan. These commands do not create a VM.

## 3. Create dedicated virtual hardware

```powershell
.\scripts\New-CanopyMintVM.ps1 -IsoPath 'C:\Downloads\linuxmint.iso' -IsoSha256 'YOUR_AUTHENTICATED_64_CHARACTER_SHA256'
```

This first checks the ISO and prints a dry-run plan. After verifying the VM name `Canopy-Test-Mint`, isolated disk path and lack of an existing VM:

```powershell
.\scripts\New-CanopyMintVM.ps1 -IsoPath 'C:\Downloads\linuxmint.iso' -IsoSha256 'YOUR_AUTHENTICATED_64_CHARACTER_SHA256' -Create
```

The script refuses to overwrite an existing VM or virtual disk. It does **not** install Linux Mint.

## 4. Probe Mint unattended installation support

Create a dedicated test-user password in a local file outside the repo, with Windows file ACLs restricted to the current user. Do not paste the password into GitHub, chat, or command-line flags.

```powershell
.\scripts\Install-CanopyMintOS.ps1 -IsoPath 'C:\Downloads\linuxmint.iso' -IsoSha256 'YOUR_AUTHENTICATED_64_CHARACTER_SHA256' -PasswordFile 'C:\private\canopy-test-password.txt'
```

If VirtualBox rejects the dry-run, stop. **Do not use `-Install`**. If it passes, that proves only VirtualBox accepts the argument configuration. The Mint installer may still require manual installation. Do not proceed with `-Install` until the exact VirtualBox/Mint version is verified.

## 5. What remains

- Confirm actual Mint Cinnamon installation, guest login, networking and snapshot `Canopy-Clean`.
- Provision `canopy-test` with a dedicated SSH public key; verify guest SSH fingerprint through an independent trusted channel.
- Run `scripts/testlab_ssh_cycle.py` with a reviewed immutable commit plan and pinned known_hosts.
- Collect independent host screenshot/window evidence and compare guest test reports.

Do not report an unattended Mint VM as PASS until these have been exercised on real hardware and retained in a run ledger.
