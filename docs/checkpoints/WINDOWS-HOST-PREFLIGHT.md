# Track: Windows host preflight for Mint VM lab (2026-11-18)

`scripts/Test-CanopyHost.ps1` provides an **optional read-only** prerequisite check for the Windows computer that will host the Linux Mint Cinnamon VirtualBox VM. It checks Windows OS, installed memory (8 GiB minimum), logical processor count (4 recommended), free host-system-drive space (60 GiB minimum), and VirtualBox CLI presence. Checks are conservative readiness thresholds, not measured performance budgets.

Windows PowerShell 5.1 or PowerShell 7:

```powershell
powershell.exe -NoProfile -File .\scripts\Test-CanopyHost.ps1 -OutputPath .\test-results\windows-host.json
```

Run its non-hardware self-test with `powershell.exe -NoProfile -File .\scripts\Test-CanopyHost.ps1 -SelfTest`. The script does NOT install VirtualBox, download Mint, enable virtualization, configure Windows startup, create VMs, collect personal identifiers or expose remote access. A missing VirtualBox reports BLOCKED (expected before installation), not a failure to execute the script.

This prerequisite is intentionally **separate** from the Mint VM's Linux `scripts/mint_preflight.py` tests. A passing Windows check does not indicate Mint is installed, operational, or accessible. GitHub-hosted Windows CI tests synthetic snapshots only; actual host assessment remains NOT RUN until the user authorizes local execution.
