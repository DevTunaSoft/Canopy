# ADR-002 — Non-disruptive GTK3 preview for Classic (provisional)

**Status:** Provisional, 2026-11-17. Does not resolve the eventual compositor or full-session architecture.

**Decision:** Build the first visible Classic features as an optional, unprivileged GTK3 application launched inside an existing Linux Mint Cinnamon session. The GTK application presents a compact top bar, menu, local clock, small dock and application launcher. The separate, standard-library-only `canopy.classic_model` contains testable display logic and future Modern can reuse shared preferences.

**Why:** The official Linux Mint developer guide documents GTK3, Python integration and Cinnamon's own JavaScript architecture. A preview that does not replace Cinnamon allows visual evaluation without modifying the display manager or user session. Gio AppInfo launches installed desktop entries without constructing shell commands.

**Explicit non-goals:** This prototype is not a compositor, window manager, GNOME/Cinnamon applet, global menu implementation, login session, display manager integration or replacement panel. The top-bar Tux icon is currently a placeholder text label. It neither hides the Cinnamon panel nor reserves layout space. Placement and styling require verification on Mint, X11/Wayland and multiple monitors.

**Risk & verification:** Local model unit tests pass, syntax compilation passes. GTK UI cannot be visually tested here because gi/GTK is unavailable. Test in Linux Mint under an ordinary user before considering packaging or autostart.

**Future:** Evaluate native Cinnamon applet/extension vs own compositor/shell and choose through a separate ADR based on complete-session requirements and measured costs. Do not infer that GTK3 is automatically the final desktop toolkit.

### 2026-11-18 launcher follow-up

Keep Gio for discovery and activation, centralize discovery policy in `canopy/applications.py`, and use GTK's native search and list controls for Classic. A Debian 13/Xvfb smoke test now covers filtering and keyboard focus. Cinnamon remains the target for manual acceptance.
