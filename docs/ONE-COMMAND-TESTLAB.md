# Canopy test-lab launcher

The supported Windows entry point is `scripts/Start-CanopyTestLab.ps1`. **This is not yet an unattended, one-click complete Mint installation.** It orchestrates the safe, implemented host-preflight and VM-hardware stages, with optional VirtualBox unattended configuration. It does not download Mint, validate GPG signatures, install VirtualBox, boot Mint, or perform actual GUI tests. Never report these stages as completed.

From a checked-out, reviewed Canopy development branch, open PowerShell at the repository root.

**Read-only host preflight (no VM changes):**
```powershell
.\scripts\Start-CanopyTestLab.ps1
```

**Create dedicated VM hardware from a locally downloaded, independently verified Mint Cinnamon ISO:**
```powershell
.\scripts\Start-CanopyTestLab.ps1 -Provision -IsoPath 'C:\Downloads\linuxmint.iso' -IsoSha256 'AUTHENTICATED_64_CHARACTER_SHA256'
```

**Optional experimental unattended configuration** (only on a newly created VM, after the exact VirtualBox/Mint compatibility is established):
```powershell
.\scripts\Start-CanopyTestLab.ps1 -Provision -ConfigureUnattended -IsoPath 'C:\Downloads\linuxmint.iso' -IsoSha256 'AUTHENTICATED_64_CHARACTER_SHA256' -PasswordFile 'C:\private\mint-password.txt'
```

**Important limitation:** The current `-Provision` path refuses an existing dedicated VM, so the optional combined unattended path is intended for a *fresh* VM. For a VM already created, run `Install-CanopyMintOS.ps1` separately after the dry-run and inspection. Do not rerun `-Provision` to recover a partial setup.

Use the official Linux Mint verification guide at https://linuxmint-installation-guide.readthedocs.io/en/latest/verify.html and never guess a checksum. The VM has an isolated virtual disk; this launcher does not repartition the Windows host. Actual Windows/VirtualBox end-to-end execution is still **NOT RUN**.
