# Canopy installer: verification and release gates

## Current truth
The Windows launcher `Canopy-Start.cmd` is **preflight only**. It does not install Linux Mint.
`Canopy-Launch-Prepared.cmd` is a separate, opt-in launcher for an **already remastered**
`canopy-*.iso` file and the existing, powered-off `Canopy-Test-Mint` BIOS VirtualBox VM.
It does not build an ISO or prove that Mint installs. Never use the remastered ISO on a physical computer:
the preseed requests automatic partitioning.

## Real ISO compatibility check (GitHub Actions)
Manually dispatch `Canopy real Mint ISO remaster validation` on the development branch,
providing the **direct HTTPS ISO URL** and **independently verified official SHA256**.
The workflow downloads and verifies the source, attempts a remaster, checks El Torito metadata,
and publishes a small verification report. It does **not** publish the large ISO, boot a VM,
or establish that Ubiquity works on Mint 22.3. A passing workflow is a remaster-only gate.

## Existing Windows VM trial
1. Keep the test VM disposable and powered off; back up anything valuable outside the VM.
2. Prepare a `canopy-*.iso` image through the Linux remaster builder using a verified source ISO.
3. Download the current repository branch to Windows and double-click
   `Canopy-Launch-Prepared.cmd`. Choose the prepared ISO and confirm the disposable-VM warning.
4. Observe the VirtualBox guest. Record whether it boots the installer, completes partitioning,
   reboots from the virtual disk, and reaches Cinnamon login.
5. If the launcher fails, retrieve the ZIP in
   `%LOCALAPPDATA%\CanopyTestLab\diagnostics`. Review the archive before sharing.

## Release blockers
- Real Mint 22.3 remaster test using an authenticated official source ISO.
- Prove BIOS boot and automatic installer compatibility, including failure paths.
- Integrate ISO preparation with a Windows double-click flow without assuming WSL is installed.
- Prevent re-running destructive installation on an already installed VM.
- Verify guest disk boot and Canopy desktop installation, usability and performance.
- Only then advertise a complete one-click installer.

Green unit tests and a successful remaster alone do not satisfy these gates.
