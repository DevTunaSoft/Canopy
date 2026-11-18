# Proposed architecture

Linux Mint foundation → existing system services/compositor integration → shared Canopy shell core (settings, performance, app model, accessibility, recovery) → interchangeable Classic / future Modern presentations.

The desktop shell runs unprivileged. Administrative actions go through existing polkit-authorized system services. No password storage or unnecessary privileged daemon. Reuse NetworkManager, PipeWire, systemd user services, portals and package-management infrastructure.

Keep Cinnamon as a selectable fallback. Version settings and migrate transactionally. Optional effects degrade gracefully. User overrides take priority over Auto Mode where safe. Never duplicate shared services across layouts.

**ADRs required before implementation:** compositor and Wayland/X11 compatibility; UI toolkit/language; packaging; settings schema; performance thresholds; login/session recovery. Evaluate memory, CPU, hardware support, maintainability and security. Universal global menus are not assumed.

The Classic preview uses `canopy/applications.py` for desktop-entry filtering, sorting and search. The module takes app descriptors supplied by the platform and has no GTK dependency. Classic owns its GTK controls and invokes the existing Gio activation path.

The preview reads its path through shared `user_settings_path()` and supports an explicit temporary built-in defaults run. This recovery path never writes the stored file. Settings migration and backup stay in the shared core design.

Classic dock selection is a layout-specific field in the shared versioned preferences model. The presentation resolves null pins to Classic defaults and renders installed desktop entries through Gio. A horizontal scroller bounds the dock to the primary work area while the Apps entry stays available. The GTK editor asks the shared settings API to update only the pins under a file lock.
