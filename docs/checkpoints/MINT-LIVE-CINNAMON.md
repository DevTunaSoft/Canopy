# Real Cinnamon X11 smoke test (2026-11-18)

Adds `scripts/mint_live_cinnamon_smoke.py` to launch the Classic GTK prototype **inside an actual Linux Mint Cinnamon user login session**, require two visible windows by PID from `wmctrl` and two independently discovered windows from `xdotool`, and terminate the launched test process. It refuses root, Wayland, Xvfb-marked tests, missing DISPLAY and non-Cinnamon session. This makes the missing Mint acceptance test an executable, fail-closed check instead of only a requirement.

After Cinnamon login and approved source checkout:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m scripts.mint_live_cinnamon_smoke --root /home/canopy-test/Canopy --output /home/canopy-test/canopy-runs/cinnamon-smoke.json
```

The user must be inside the active graphical session; an SSH shell may not have session DISPLAY/XAUTHORITY. A dedicated graphical session auto-login or a properly authorized per-user worker is still to be provisioned and tested, **not implied**. The script does not perform keyboard/mouse actions or compare screenshots yet. Synthetic unit tests only; real Mint Cinnamon execution NOT RUN. This track is independent of unattended ISO installation and other test paths.
