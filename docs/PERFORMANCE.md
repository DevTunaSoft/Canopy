# Canopy performance budget and verification

All numbers below are **targets, not measured results**.

| Metric | Initial target | Verification |
| --- | --- | --- |
| Idle full desktop memory | ≤ 1 GiB resident total desktop-related footprint on reference hardware | Capture PSS/RSS per process and sum scope; report kernel/cache separately |
| Idle CPU | ~0–2% on reference hardware | 10-minute sampled steady state after boot, distinguish system-wide and Canopy-specific |
| Refresh/motion | 60 fps where supported | Frame-time trace and dropped frame counts on integrated graphics |
| Minimum target hardware | 4 GiB RAM for basic desktop use | Boot, launch file manager/browser, application switching, report swap |
| Animation idle overhead | no continuous updates | compositor and Canopy process wakeup and CPU traces |
| Low-effects mode | equal usability | visual/keyboard/accessibility comparisons |

Do not promise universal thresholds: CPU performance, graphics drivers, display resolution and Linux stack all influence results.

## Test matrix
- 4 GiB / low-end integrated GPU; 8 GiB / entry desktop; 16 GiB / standard desktop.
- 1366×768 and 1920×1080, high DPI, single and dual display.
- Light/dark, launcher open/closed, docks hidden/visible, 20+ windows, sleep/resume.
- Native-app and third-party-app mix.
- Cold boot, settled idle after 5 minutes, 10-minute steady idle, browser plus file-manager multitasking.

## Recording protocol
Record distro and kernel, desktop/compositor versions, GPU/driver, screen count, render backend, memory pressure, CPU frequency, temperature, measurement command and raw output. Run ≥3 repeats and note variance. Root-cause regressions and preserve before/after trace artifacts.

## Degradation ladder
1. Shorten animation and reduce staggered transitions.
2. Disable live backdrop blur while maintaining semi-opaque flat surfaces.
3. Use static shadow assets and skip secondary adornments.
4. Do not disable essential accessibility or navigation behaviors.

## Release gate
No performance claim may be marked PASS without an actual Linux session, test hardware/environment metadata and reproducible logs. Static design preview results are never performance evidence.
