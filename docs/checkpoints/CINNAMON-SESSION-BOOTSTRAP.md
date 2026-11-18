# Disposable Mint VM Cinnamon graphical session automation

`scripts/Enable-CanopyGuestCinnamon.sh` is the explicitly authorized **one-time** configuration of Cinnamon login for the restricted `canopy-test` user. It refuses non-Mint and non-VirtualBox machines, rejects root/other users, preserves existing LightDM configuration, and creates its own drop-in. This permits future GUI tests to run when the VM boots without requesting mouse clicks. Autologin is intentionally only for a disposable VM: anyone with console access can enter the account, so no personal files or host secrets should be shared with it.

After normal Mint OS install, dedicated account creation and initial trusted guest setup, run once:
```bash
bash scripts/Enable-CanopyGuestCinnamon.sh --enable
```

`scripts/cinnamon_guest_session.py` discovers the actual owned `cinnamon` process in `/proc`, extracts its limited display/session environment and requires an owned Xauthority file. It then launches `scripts.mint_live_cinnamon_smoke` in that environment, requiring both `wmctrl` and `xdotool` to independently find two Classic preview windows. Host-initiated SSH can run this without an interactive terminal in the guest **after the above VM onboarding is complete**. No Xvfb or Wayland substitution qualifies. This is still guest-level evidence and cannot replace host screenshot and reboot observation.

**Real Mint Cinnamon autologin, Xauthority file location, and process-environment access have NOT RUN.** The VM ISO install and first-boot onboarding remain unverified. There is no verified way to bypass these prerequisites, and no silent fallback to insecure access is permitted.
