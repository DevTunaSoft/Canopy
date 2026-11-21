# Canopy Shell Packs — extensible desktop experience contract

**Status: DESIGN CONTRACT + OFFLINE MANIFEST VALIDATOR ONLY.** Neither a
runtime plugin loader, cross-shell hot swap nor a plugin marketplace is
implemented. This design does not replace the existing Classic prototype,
and does not authorize a LacOS release claim.

## Product promise: more than two desktops

Classic and Modern are the first two **Shell Packs**, not hardcoded limits.
Future contributors should be able to build a wholly new desktop experience
(e.g. minimal, accessibility-focused, creator-focused) without forking Canopy,
rewriting the app launcher, replacing Mint, or starting a second compositor.
Let Linux newcomers select a familiar interface and later explore others.

A Shell Pack is a **presentation adapter** for the Canopy host. It is *not*
an independent Linux distribution, window manager, Wayland compositor or a
new Linux desktop session unless explicitly categorized otherwise.

## Proposed architecture

```text
     Canopy settings: choose/switch Shell Pack
                     |
          Session + Shell Host (one active)
         /           |             \
   Classic Pack   Modern Pack    Future Pack(s)
         \           |             /
      stable versioned Shell Host API
          |             |            |
   app launcher      windows      notifications / settings
          \             |            /
     shared system services and compositor/session integration
                  Linux Mint / LacOS
```

The **host** alone owns the compositor/window-management integration, session
lifecycle, service access, app/window identity, central settings and recovery.
A pack owns its UI layout, original artwork, component-specific preferences
and permitted visual behavior. A pack may request service data and perform
permitted user actions via host capabilities, but must not reimplement or
launch a parallel system tray, notification daemon, compositor or app index.

A pack can be made with Qt/QML (current prototype path). A non-QML adapter
may be supported through an **explicit versioned IPC bridge** later, only
after resource, accessibility, safety and performance acceptance. Do not
pretend GTK or third-party desktop environments are hot-swappable through
the QML loader.

## Shell Pack v1 draft manifest

Each standalone pack contains `manifest.json` and a UI entrypoint. The
initial offline checker in `tools/check_shell_pack.py` enforces the draft
metadata contract; the runner does **not load or execute** UI code.

```json
{
  "manifest_version": 1,
  "id": "org.example.canopy.minimal",
  "name": "Minimal Example",
  "description": "Starter for a new Canopy desktop layout",
  "shell_api": 1,
  "kind": "presentation",
  "ui_engine": "qt-qml",
  "entrypoint": "ui/Main.qml",
  "capabilities": ["app-launcher", "workspace-list"],
  "switch_strategy": "same-session",
  "permissions": []
}
```

- `manifest_version`: version of metadata shape; reject unknown versions.
- `id`: unique reverse-DNS-style identity used for settings, upgrades and
  persisted selection; cannot impersonate reserved built-in identities.
- `shell_api`: required stable host API major version. Reject mismatches,
  never silently assume compatibility; minor capabilities are negotiated.
- `kind`: `presentation` only in v1. New compositor/session packs need a
  separate trust model, install flow and explicit logout-only semantics.
- `ui_engine`: `qt-qml` in this first contract, **not** a final decision
  to forbid other toolkits or IPC adapters.
- `entrypoint`: relative, in-pack, real file; never an absolute path,
  external URI or symlink.
- `capabilities`: requested host UI affordances; allowlisted and uniquely
  specified. These are **not system permissions**.
- `switch_strategy`: `same-session` is the pack's intended mode only; it
  is **not proof** switching works. The host decides using the actual
  compositor/session compatibility matrix.
- `permissions`: empty in v1. No pack gets root, shell process execution,
  arbitrary filesystem access or system DBus permissions via this manifest.
  Future non-empty permissions require a separate reviewed specification.

Malformed, unsupported, oversized, duplicate-key or path-escaping manifests
fail closed. Manifest validation is **not equivalent to code signature
verification, sandboxing or permission enforcement**. Never install or execute
untrusted third-party QML based only on a valid JSON file.

## Host API boundaries (design, not yet implemented)

A future `ShellHost v1` should provide versioned, typed, capability-gated,
asynchronous interfaces: `Apps.list/search/launch`,
`Windows.list/focus/minimize`, `Workspaces.list/select`,
`Notifications.summary`, `SystemStatus.snapshot`,
`Settings.read/update`, and `Accessibility.preferences`.
No pack receives private tokens or global unrestricted DBus access.
The host owns event subscriptions with explicit unsubscribe on deactivation.

The mode transition is **transactional**:
1. Validate installed pack, compatible API, provenance and capabilities.
2. Save current mode's presentation preferences, prepare target *offscreen*
   within a bounded memory/time budget (never initialize a second desktop).
3. Transfer UI ownership to target only when healthy; leave running
   applications and their compositor-owned windows untouched.
4. Unsubscribe and release old UI, measure retained memory and wakeups,
   persist new mode and confirm accessibility/focus correctness.
5. On any failure, reactivate the original shell without losing active
   windows or user data. After repeated failure, offer recovery UI.

If a proposed pack requires changing compositors or desktop sessions, offer
a **clearly warned logout/login route**, never a fake seamless live switch.
No mode switcher is implemented yet.

## Developer experience: how to add a shell

1. Copy `examples/shell-pack-starter` into a new local pack directory.
2. Change `manifest.json` ID, display name and declared capabilities.
3. Replace only the starter `ui/Main.qml` with an original, accessible,
   responsive interface that consumes the shared host APIs once available.
4. Run `python3 tools/check_shell_pack.py path/to/new-pack`.
5. Run `python3 -m unittest tests.test_shell_pack -v`, source lint,
   actual Qt screenshot and performance checks, and Mint VM acceptance.
6. Publish as a versioned, audited, properly licensed package when secure
   install/discovery and signing are actually built.

A starter pack's successful validation **does not make it installable**.
Current Classic is a standalone Qt demo and **has not been migrated** to
this pack protocol. Modern is planned, not a second running shell. This
separation avoids misleading users about existing functionality.

## Non-negotiable acceptance for every additional shell

- Premium, coherent, original/licensed icons, wallpaper, typography,
  responsive layouts, HiDPI, light/dark/high contrast, keyboard-only and
  screen-reader accessibility, reduced motion.
- Zero extra always-on desktop services for inactive packs; lazy load UI,
  bounded caches, resource measurements against the Classic baseline.
- App and window state preserved for supported live switches; repeated
  A→B→A stress tests, crash injection and rollback evidence.
- Explicit version compatibility, safe upgrades, no privileges by default,
  signed package verification *before* any community-code execution.
- Linux Mint and (future) LacOS end-to-end tests, clear PASS/FAIL/BLOCKED
  reporting, human visual approval, and no changes to previously approved
  Classic artwork without fresh authorization.

## Roadmap boundary

**Now:** document versioned boundaries, build the offline validator and
starter, continue finishing Canopy Classic. **Later:** implement host service
interfaces, adapt Classic, make Modern as the *second* pack, introduce the
switcher and compatibility testing, then test third-party pack loading.
**Much later:** LacOS distribution packaging and optional trusted pack
catalog. No plugin marketplace, hot-swap runtime or distribution exists yet.

## Bounded offline registry (implemented building block)

`canopy_core.registry.scan_shell_packs(catalog)` enumerates a bounded local
catalog, validates each direct pack folder against the v1 manifest contract,
rejects symlinks, unsafe manifests and **all instances of duplicate IDs**, and
returns immutable metadata plus separately reported errors. It does **not**
import or instantiate UI code. `python3 -m canopy_core examples --json`
emits a structured report with `trusted: false` and
`runtime_loading_enabled: false`; errors cause a nonzero exit status.

The registry is a tested **metadata discovery component**, not a shell loader,
installer, trust evaluator, live mode switcher or authorization to execute
third-party QML. A future host must verify packages and isolate/authorize
execution before ever consuming catalog entries as runnable components.

## Trusted-host lifecycle coordinator (prototype, no Qt integration)

`canopy_core.shell_host.ShellHost` now implements an **in-memory lifecycle
state machine for explicitly host-registered, reviewed presenters only**.
It validates target metadata and requested capabilities against the catalog
and host allowlist, prepares a candidate, deactivates the old view before
activating the new one, disposes the old view, and attempts rollback if
activation fails. Three distinct mock presentations are tested without
hardcoding Classic/Modern. Reentrant transitions are rejected. Unknown or
untrusted metadata entries **cannot** make the host load arbitrary code.

A failed partial activation or failed rollback sets a recovery-required
state rather than pretending a seamless switch worked; failure to dispose
an old presenter is surfaced as a cleanup failure, not a false green result.

**Limits:** this is a pure-Python prototype with inert test presenters. It is
not connected to the compiled Qt application or Mint session; it does not
own real compositor windows or preserve app state, sandbox plugins, verify
signed packages, execute QML or deliver end-user live switching. The future
Qt host will need an equivalent verified lifecycle/API implementation with
real crash/restart, window, display and memory tests.
