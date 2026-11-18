# Independent Mint readiness preflight — 2026-11-18

A read-only tool now provides explicit PASS/BLOCKED checks for Mint identity, non-root operation, Python, Git, Xvfb, GTK3 introspection, Cinnamon desktop and X11 DISPLAY. The script never installs packages, changes a login session, opens an app, connects to Windows or gathers full desktop screenshots. It reports structured JSON.

```bash
python3 scripts/mint_preflight.py --output test-results/mint-preflight.json
```

Run **inside the intended Mint Cinnamon VM user session**, not on a generic GitHub Ubuntu runner. The Cinnamon and X11 prerequisites are for the initial Classic acceptance path; later Wayland work will require separate checks. Linux Mint desktop and VM preflight have NOT RUN, so no PASS claim on Mint is authorized. Standard-library synthetic tests only. Follow the existing security instructions for an isolated, approved-commit test worker.

This track edits no shared runner, GTK or approval-gate modules, and should be reviewed separately from other tracks.

## X11-session correctness regression

A reviewer identified a false-positive path: a Wayland desktop can expose an XWayland `DISPLAY=:0` even though the native session is not X11. The preflight now additionally requires `XDG_SESSION_TYPE=x11` and accepts both `Cinnamon` and `X-Cinnamon` desktop tokens. A regression test explicitly covers the Wayland-plus-DISPLAY case. This gate applies to the X11 Classic test target only; it is not a rejection of future Wayland support.
