# ADR-003 · Classic session integration candidates

## Status

Proposed on 2026-11-18. Keep the optional GTK preview and evaluate Cinnamon integration first on Linux Mint. The production session, compositor, toolkit and packaging choices remain open.

## Context

Canopy Classic needs a top bar, dock, app discovery and window workflows. A selectable Canopy session must preserve the existing Cinnamon login and share services with future Modern. The current GTK preview exercises user interface and Gio integration inside a graphical session. The X11 results cover two ordinary GTK windows and do not establish session behavior.

## Options

| Option | Compatibility and resource implications | Safety and maintenance |
|---|---|---|
| Cinnamon applet or extension | Reuses Cinnamon and Muffin for window policy, shortcuts and display handling. Evaluate a per-user applet on the target Mint release. X11 and Wayland behavior depends on that release. Incremental cost must be measured on top of the same Cinnamon baseline. | An applet can start with fewer changes to the current session. Code loaded into Cinnamon's shell shares its fault domain. Treat a separate login session with independent settings and crash containment as a separate engineering problem. |
| Independent shell and compositor | Offers control over placement, effects and window workflows. Canopy would take ownership of backend integration, protocols, XWayland, scaling, accessibility plumbing and GPU compatibility. Total resource cost is unknown. | Requires the largest implementation, maintenance and hardware test effort. Needs separate packaging and recovery design. Defer until a requirement rules out both reuse options. |
| Independent presentation on Labwc | Labwc supplies a Wayland stacking compositor and leaves panels, screenshots and other desktop services to clients. Evaluate XWayland for existing apps and protocol support for panel placement, shortcuts, window metadata and application switching. Total cost includes all companion services. | A separate session can keep Cinnamon available. Canopy would still own startup, session cleanup, portals, notifications, lock screen, power and recovery integration. Test these before proposing installation. |

Global menus require support from the individual application or toolkit. Evaluate this independently from the panel backend. Nemo and other default applications continue to launch through existing desktop entries. Verify their behavior in a candidate session before treating the file manager or file associations as integrated.

Sources for candidate capabilities include the Cinnamon applet and extension managers, the Muffin upstream description and Labwc's scope. [Cinnamon](https://github.com/linuxmint/cinnamon/tree/master/js/ui) · [Muffin](https://github.com/linuxmint/muffin) · [Labwc](https://github.com/labwc/labwc)

## Evidence and evaluation gates

On Debian 13, the GTK3 preview passed a headless X11 smoke test covering startup with missing dock apps, launcher keyboard focus, dock placement, window cleanup and the menu image. A spot measurement on commit `12cc7bd` used three fresh system Python processes under the same Xvfb display. Time from the first Python statement until the first GTK idle callback was 3,226–3,305 ms. Peak process RSS at that callback was 70,072 KiB in all three runs. Process CPU over the next five seconds was 0.01–0.03% of one core. These figures include GTK initialization, exclude the display server and Cinnamon, and leave disk I/O and power unmeasured. The environment and sample size preclude setting a budget.

The first target trial requires a disposable Mint Cinnamon session. Verify the preview's interaction with the existing panel and then try an opt-in per-user applet with a minimal launcher and dock interaction. Record the exact Mint release, display backend, hardware and test steps. Compare repeated cold and warm startup, idle RSS and CPU, dialog responsiveness, and cleanup against the same Mint installation with the applet disabled. Check keyboard navigation, focus, screen reader operation, missing app IDs, monitor offsets and scaling. Test stopping the preview or removing the applet and signing back into stock Cinnamon.

Use a separate disposable login session or nested compositor for the Labwc trial if the Cinnamon trial cannot demonstrate a maintainable path to a distinct, recoverable session. Confirm XWayland, native Wayland apps, screen locking, suspend/resume, portals and logout before recommending it. Run Intel, AMD and NVIDIA trials before accepting a compositor choice.

Keep application discovery and preferences in the shared core. Prototype-only Cinnamon or Wayland integrations belong in presentation or platform adapters. Neither candidate changes the versioned settings contract. Existing Cinnamon remains the recovery path.
