# Windows one-command bootstrap preparation (2026-11-18)

`scripts/Install-Canopy-TestLab.ps1` is the *safe pre-provisioning stage* of the promised one-script Mint lab installer. This stage invokes the existing Windows read-only host probe from PR #27, writes host readiness JSON and a five-stage plan to `%LOCALAPPDATA%\CanopyTestLab`, and exits BLOCKED when prerequisites are insufficient. It currently **does not install VirtualBox, download/verify Linux Mint, create a VM, configure a guest agent, give the assistant remote access, or set scheduled tasks**. Its name is intentional for the future final entrypoint, but do not claim that the installer is fully functional.

Once branches are integrated into one approved checkout, execute:
```powershell
powershell.exe -NoProfile -File .\scripts\Install-Canopy-TestLab.ps1
```

For a no-hardware self-test: `powershell.exe -NoProfile -File .\scripts\Install-Canopy-TestLab.ps1 -SelfTest`. This script depends on `scripts/Test-CanopyHost.ps1` currently in separate PR #27; run from an integration checkout that includes both. A Windows GitHub Actions self-test provides syntactic and synthetic confidence; a real Windows host run is still NOT RUN. **Future implementation** must use pinned official downloads with verified signed checksums, consent before host changes, a reversible installer and a dedicated VM. Do not bypass checks to make a one-click appearance.
