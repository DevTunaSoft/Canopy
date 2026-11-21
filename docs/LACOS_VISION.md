# LacOS — future Linux Mint-based distribution goal

**Status: PLANNED / NOT IMPLEMENTED.** LacOS is a working product name, not a released operating system. Canopy remains the separately usable Linux desktop shell. LacOS becomes a distinct Linux Mint-based distribution project only **after** the Canopy shell is technically reliable, visually approved, benchmarked, and accepted in real Linux Mint sessions.

## Mission
Build a premium, familiar Linux experience for people migrating from **macOS or Windows**, retaining the proven Mint/Linux compatibility, update and security foundations while making the result **leaner, more refined, more capable, and more adaptable**. The goal is measurable functional improvement with *lower total resource usage*, not a superficial theme or indiscriminate removal of components.

## One system, freely switchable desktop experiences
- **Canopy Classic:** polished macOS-familiar navigation, menu bar, dock, and workflows using **original or properly licensed** assets.
- **Canopy Modern:** equally polished Windows-familiar taskbar, application launcher, system tray, snapping, window workflows, and shortcuts; original or properly licensed assets.
- Both are different presentation/shell modes on a **single shared set** of window/session services, application state, settings contracts and compositor integration where technically practical. **Never** run two complete competing desktops or duplicate background services simply to enable switching.
- **A user can switch Classic ↔ Modern whenever desired**, from an accessible system-settings/desktop action, not only at installation. Switching back is always supported. Default installation choice is only an initial preference.
- **Target:** live, in-session switching without a reboot or reinstall, preserving running apps, windows, and user work. Validate this with real application/session tests; don't claim it works until demonstrated. Preserve independent per-mode customization atop shared system settings.
- **Fallback:** if an underlying compositor/session must change or a third-party desktop environment is selected, safely offer a logout/login transition with clear notice. Never silently terminate user apps or promise universal cross-DE live swaps.
- Switching failure must recover the prior usable presentation without data loss; switching must not require a continuously running second shell.

## Unlimited future desktop experiences: Shell Packs

**Classic and Modern are starting examples, not a two-mode ceiling.** Canopy
should welcome people to Linux by offering new, original and accessible
presentation options over time: minimal, creator-focused, education-friendly,
accessibility-first or community-designed experiences. Anyone building a new
experience should work on a **Shell Pack**, not fork LacOS or duplicate a
desktop services stack.

A future Shell Pack must declare a unique identity, compatible versioned host
API and UI entrypoint, requested UI capabilities and intended switch model.
The host discovers compatible, trusted installed packs and presents a
clear, accessible chooser with screenshots and the ability to revert.
Inactive packs consume no persistent desktop services. Classic remains the
default proven reference until other modes pass their own acceptance.

Keep core app launching, window/session ownership, notifications, settings,
system status, power/lock state and permission checks in one shared host.
Future packs own their own visual layout, artwork and per-pack preferences.
Use a versioned, toolkit-neutral contract where practical; v1's Qt/QML
adapter is a starting implementation, not a permanent requirement for every
future toolkit. Untrusted community contributions must not execute or gain
privileges merely because a manifest is valid.

Switch between compatible presentation packs in-session when real compositor,
state and lifecycle tests prove it. Third-party full DE/compositor changes may
require a warned logout/login transition; do not mislabel them as seamless
shell swaps. Plugin discovery/loading, live switching and a community catalog
are future work, not implemented features. See
[the Shell Pack architecture](SHELL_PACK_ARCHITECTURE.md).

## Resource efficiency and added functionality
- Prioritize **measured idle RAM/CPU/GPU use, wakeups, startup, responsiveness, sustained memory growth, battery/power behavior**, and cold/warm transitions. Compare LacOS with stock Mint on the **same hardware and workload**, with methodology and exclusions recorded.
- Preserve Mint's package ecosystem, security updates, accessibility, hardware support, recovery paths, and user data. Remove or replace a component only after dependency review, performance evidence, rollback planning, and regression testing.
- Extend Canopy's **five performance profiles plus Auto Mode**, with per-feature overrides and event-driven/lazy-loading behavior; do not force graphical effects or unused features to run in the background.
- Add genuinely useful integrated functionality: cross-platform-familiar application discovery, keyboard shortcuts, file workflows, system controls, window management, migration assistance, and sensible defaults. Features must justify maintenance, security and resource cost.
- Visual quality is a release gate: premium original light/dark designs, coherent icons and typography, HiDPI, keyboard/screen-reader accessibility, reduced motion, and actual user-reviewed screenshots. A green CI check is not visual acceptance.

## Sequencing and delivery gates
1. **Finish Canopy Classic first:** working, high-quality, validated shell/session with approved visual assets, real Mint VM and hardware acceptance, performance/regression evidence.
2. **Build Canopy Modern:** reuse the Classic core; validate Windows-familiar behavior, accessibility, performance and styling independently.
3. **Implement and verify the Shell Pack switcher:** session-preserving Classic/Modern and later additional approved packs, safe fallback, rollback, persistent per-pack preferences, no duplicate services.
4. **Branch LacOS as a separate distribution:** a maintained Mint-derived installer/image with both modes, appropriate installer onboarding, upgrade/recovery tooling and measured optimizations.
5. **Release only after acceptance:** reproducible builds, security/update compatibility, real hardware coverage, low-end and modern systems, repeatable stock-Mint comparison, both modes and repeated switch/restore stress tests.

**Non-goals:** reimplement the Linux kernel/package manager unnecessarily; copy Apple/Microsoft trademarks or assets; replace Mint stability with unsafe "debloating"; claim a release, performance win or seamless shell swap before it is proven.

This goal **adds to**, and does not replace, the existing architecture, quality budgets, agent rules, asset provenance and visual-review requirements.
