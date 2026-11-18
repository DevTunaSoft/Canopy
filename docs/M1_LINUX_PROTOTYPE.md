# M1: First real Linux desktop prototype

Status: **NOT RUN**. This is an implementation and acceptance plan, not a working desktop.

## Foundation comparison
- **Linux Mint Cinnamon**: officially supported Mint edition, likely simplest packaging and update path.
- **Linux Mint Xfce**: officially supported Mint edition; benchmark possible lower overhead versus additional UI integration effort.
- **KDE Plasma on a KDE-supported distribution**: assess native dock, launcher, compositor, theme and window integration. KDE is **not** an official Linux Mint edition in current Mint release downloads.

Do not choose by concept art. Compare real installation, maintainability, keyboard accessibility, cohesive application styling, and idle/multitasking performance.

## Milestone sequence
1. Record a clean baseline on 4GB and 8GB test systems; capture distro, session, compositor, GPU, display resolution/scaling, per-process PSS, desktop CPU, idle wakeups and frame timing.
2. Build a disposable/non-destructive Classic prototype on the selected desktop: original Canopy logo, top bar, bottom dock, application launcher, file manager theme.
3. Preserve standard distro recovery and session chooser. Theme/layout application must be reversible and avoid touching user-owned settings irreversibly.
4. Capture **real screenshots from the running Linux desktop** at 1366x768 and 1920x1080, light/dark and 100%/150% scaling. Review against `docs/VISUAL_QUALITY_GATE.md`.
5. Measure after changes; compare with pre-C anopy baseline in the same hardware environment. Do not claim the <=1GiB RAM, ~0–2% idle CPU or 60 FPS goals without verified measurements.
6. Test keyboard-only use, reduced-motion, high DPI, long text, sleep/resume, fresh login, task switching and responsiveness under load.
7. Only after evidence-backed acceptance: prototype a reproducible installer/ISO build.

## Read-only baseline helper
Run `python3 tools/canopy_baseline.py --seconds 10 --output baseline.json` on a Linux test system to collect a scoped process snapshot. It reads /proc and writes only the named JSON file. **Limitations:** captures only selected desktop processes, cannot measure GPU memory or frame times, PSS may be inaccessible, and a short sampled CPU percentage is not a validated steady idle average. Repeat 3+ times after desktop idle settles, gather full machine context separately, and avoid sharing private logs without review.

## Exit criteria
- [ ] Desktop foundation decision supported by recorded comparison.
- [ ] Real Canopy Classic session with working controls.
- [ ] Original licensed icons and polished light/dark theme.
- [ ] Linux-native screenshots attached with runtime evidence.
- [ ] Accessibility and functional regression results recorded.
- [ ] Resource/performance results collected on low-end hardware.
- [ ] Safe rollback/recovery tested.
- [ ] Installation packaging milestone authorized after gates pass.

Any unverified step remains **NOT RUN**, never PASS.
