# Unattended Windows host scheduler — 2026-11-18

`scripts/Enable-CanopyTestLabSchedule.ps1` is the opt-in Task Scheduler setup for the existing one-shot host supervisor. It registers exactly one `CanopyTestLab-ApprovedTests` task, owned by the **currently logged-in Windows user**, with **limited rights** and interactive logon (no stored password or SYSTEM account). Runs every 30 minutes for a finite scheduling window; new setup or renewal is required after the first year. Prevents concurrent instances and caps execution time. Disable operation removes only its dedicated task.

```powershell
powershell.exe -NoProfile -File .\scripts\Enable-CanopyTestLabSchedule.ps1 -RepoPath C:\CanopyLab\Canopy -ConfigPath C:\CanopyLab\host-config.json -Enable
```

Disable: `powershell.exe -NoProfile -File .\scripts\Enable-CanopyTestLabSchedule.ps1 -Disable`. Synthetic self-test: `powershell.exe -NoProfile -File .\scripts\Enable-CanopyTestLabSchedule.ps1 -SelfTest`.

This **must not be activated before** Windows host config, dedicated VM UUID, SSH identity and trusted pinned known_hosts file, isolated guest login, and approved immutable plan exist. The scheduled task uses Python from the host PATH. The computer must stay powered on and **the Windows user must remain logged in** for the Interactive task. A secure logoff-capable service account would require separate provisioning and authorization; no credentials are requested or stored here. No arbitrary PR code or host-wide services are enabled.

The supervisor returns `PASS_TEST_SUITE_NOT_RELEASE` only for a checked suite, not complete desktop certification; real Mint host/guest and task scheduling acceptance have NOT RUN.
