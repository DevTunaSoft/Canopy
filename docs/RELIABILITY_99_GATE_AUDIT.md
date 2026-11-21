# Canopy / LacOS — 99-angle functional reliability gates

**Review state:** 2026-11-21 — initial source/CI reconnaissance against public `DevTunaSoft/Canopy` main and draft Classic PRs #100 / #102. **This is an acceptance matrix, not 99 completed tests.** No claim of zero bugs, full Mint VM acceptance or an approved final icon appearance.

## Classification
- **CI-SCOPED:** A relevant specific test or compiled runtime check passed in GitHub Actions or code-unit tests. **Only that scoped behavior is evidenced**, not full Linux Mint behavior. Relevant runs: [Qt CI #44873903253](https://github.com/DevTunaSoft/Canopy/actions/runs/44873903253), [Foundation checks](https://github.com/DevTunaSoft/Canopy/actions).
- **GAP:** No end-to-end proof or implementation of the required user-visible behavior; verify and build.
- **BLOCKED:** Real Mint VM, external original art, explicit aesthetic acceptance, or other real environment evidence not available in the current automation.

`P0` = release blocker, `P1` = significant quality gate, `P2` = later compatibility/development gate. A P0 entry cannot be marked complete based solely on a successful source test or 5-second Ubuntu smoke test. **All statuses are initial and must be reverified per exact commit/guest environment.**

The two specific defects discovered in this review are addressed by [PR #104 (skipped CI checks)](https://github.com/DevTunaSoft/Canopy/pull/104) and [PR #105 (incomplete Shell Host cleanup)](https://github.com/DevTunaSoft/Canopy/pull/105). Both were verified and merged; this does not resolve remaining functionality gaps.

## Session & compositor

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R001 | P0 | GAP | A genuine Linux Mint desktop session starts Canopy as an alternative session |
| R002 | P0 | GAP | One compositor owns windows and rendering throughout a session |
| R003 | P0 | GAP | Canopy cannot accidentally duplicate Cinnamon window management |
| R004 | P0 | GAP | Users can return safely to the original Mint session |
| R005 | P0 | GAP | All running application windows remain intact during supported mode switches |
| R006 | P1 | GAP | Session state survives logout/login when a cold switch is required |
| R007 | P1 | GAP | Window focus and z-order match active presentation transitions |
| R008 | P1 | GAP | Hot-plugging and unplugging monitors does not strand windows |
| R009 | P1 | GAP | X11 and Wayland backends are explicitly supported or safely rejected |

## Lifecycle, recovery & fault injection

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R010 | P0 | CI-SCOPED | The host prepares a candidate before deactivating the current presenter |
| R011 | P0 | CI-SCOPED | Activation failure restores the prior presenter when cleanup succeeds |
| R012 | P0 | CI-SCOPED | Failed disposal freezes subsequent host transitions |
| R013 | P0 | CI-SCOPED | Reentrant switch requests are rejected deterministically |
| R014 | P0 | GAP | Hard process crashes are caught and session recovery is functional |
| R015 | P0 | GAP | Out-of-memory termination cannot trap users without a desktop |
| R016 | P1 | GAP | Sleep/resume restores interactive state and input focus |
| R017 | P1 | GAP | Failed-recovery state has an implemented safe user exit |
| R018 | P1 | GAP | Transition fuzzing covers random callback failures and repeated mode changes |

## Extensible Shell Packs

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R019 | P0 | CI-SCOPED | Pack metadata schema and host major-version mismatch are validated |
| R020 | P0 | CI-SCOPED | Duplicate pack identities and path escapes are rejected |
| R021 | P0 | CI-SCOPED | A third sample pack can be discovered without changing core code |
| R022 | P1 | CI-SCOPED | Local starter scaffolding avoids overwriting existing user files |
| R023 | P0 | GAP | A running host consumes a stable, capability-checked pack API |
| R024 | P0 | GAP | Untrusted community QML cannot access unrestricted host services |
| R025 | P1 | GAP | Toolkit adapters have versioned IPC rather than uncontrolled processes |
| R026 | P1 | GAP | Pack upgrade, disable and rollback preserve prior working selection |
| R027 | P2 | GAP | A catalog can scale past the current 64-entry offline scan bound safely |

## Security, trust & adversarial inputs

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R028 | P0 | CI-SCOPED | Manifest duplicate keys, invalid permissions and symlink paths are rejected |
| R029 | P0 | GAP | Signature and publisher provenance are verified before pack execution |
| R030 | P0 | GAP | QML plugin isolation prevents arbitrary file and D-Bus access |
| R031 | P0 | GAP | Runtime capability permissions are enforced, not merely described |
| R032 | P0 | GAP | Untrusted updater/installer paths cannot gain elevated privileges |
| R033 | P1 | GAP | Filesystem TOCTOU races and symlink replacements are fuzz-tested |
| R034 | P1 | GAP | Pack archives reject zip slips, decompression bombs and dangerous links |
| R035 | P1 | GAP | Dangerous desktop-entry or URL protocols cannot bypass launch policy |
| R036 | P1 | GAP | Dependency, SBOM and vulnerability scanning gate releases |

## Applications, dock & window behavior

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R037 | P0 | CI-SCOPED | An opt-in desktop-entry launcher rejects arbitrary dock input |
| R038 | P0 | CI-SCOPED | A harmless actual GIO desktop entry can launch under Ubuntu CI |
| R039 | P0 | BLOCKED | Nemo, Firefox and Terminal open and focus correctly on real Mint |
| R040 | P0 | GAP | The dock lists real running applications rather than demo placeholders |
| R041 | P1 | GAP | App launch failures give actionable in-UI feedback |
| R042 | P1 | GAP | Multiple windows, duplicate launches and recent apps behave predictably |
| R043 | P1 | GAP | Global shortcuts do not conflict with Cinnamon or accessibility keys |
| R044 | P1 | GAP | Window close/minimize/maximize semantics work outside the preview |
| R045 | P2 | GAP | Application icon badges, progress and unread state use shared services |

## Visual quality & asset provenance

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R046 | P0 | CI-SCOPED | Original eight-icon SHA-256 manifest is validated when art is supplied |
| R047 | P0 | BLOCKED | All eight icons are optically balanced in an owner-accepted actual Qt screenshot |
| R048 | P0 | BLOCKED | The refined Terminal variant is reviewed without replacing its original master |
| R049 | P1 | CI-SCOPED | The Qt preview captures valid 760x500, 1200x750 and 1920x1080 PNGs |
| R050 | P1 | BLOCKED | A Mint guest renders the approved wallpaper and original icon set |
| R051 | P1 | GAP | Fractional scaling and HiDPI maintain sharpness and icon geometry |
| R052 | P1 | GAP | Light, dark and high-contrast variants remain consistently polished |
| R053 | P1 | GAP | Visual diff baselines reject unwanted changes to other UI areas |
| R054 | P2 | GAP | Multi-monitor wallpaper, blur and transparency stay resource-efficient |

## Accessibility & internationalization

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R055 | P0 | GAP | Every primary control is usable by keyboard only |
| R056 | P0 | GAP | The real dock reports clear accessible names and states to a screen reader |
| R057 | P0 | GAP | Text and icons meet measured contrast at all supported themes |
| R058 | P1 | GAP | Focus survives opening/closing windows and switching shells |
| R059 | P1 | GAP | Reduced-motion settings disable unnecessary transitions |
| R060 | P1 | GAP | System font scaling works without clipping or broken menus |
| R061 | P1 | GAP | High-contrast mode does not depend solely on color |
| R062 | P2 | GAP | Long translated labels, RTL layouts and locale dates fit |
| R063 | P2 | GAP | Touch, keyboard, mouse and high-DPI pointer targets are tested |

## Resource efficiency & stability

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R064 | P0 | GAP | Five user-selectable performance profiles and Auto Mode work |
| R065 | P0 | GAP | No inactive shell keeps duplicate desktop services running |
| R066 | P0 | BLOCKED | Five-minute idle CPU, PSS and wakeup metrics are recorded on Mint |
| R067 | P1 | CI-SCOPED | Short informational Qt CPU/PSS sampling runs on Ubuntu Actions |
| R068 | P1 | GAP | Cold start, warm start and responsiveness have reproducible budgets |
| R069 | P1 | GAP | Repeated shell switching has no retained subscriptions or memory leak |
| R070 | P1 | GAP | Integrated/discrete/VM/software GPU fallback behaves gracefully |
| R071 | P1 | GAP | Low-spec 4GB RAM guests remain responsive under realistic app load |
| R072 | P2 | GAP | Battery, suspend and thermal workloads are benchmarked |

## Linux Mint installation & recovery

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R073 | P0 | CI-SCOPED | In-guest preflight distinguishes Linux Mint from Ubuntu |
| R074 | P0 | BLOCKED | Mint 22.3 Cinnamon builds and launches the exact Qt source revision |
| R075 | P0 | GAP | A reversible per-user installation mechanism is verified |
| R076 | P0 | GAP | Installer never replaces default login manager without explicit consent |
| R077 | P0 | GAP | Uninstall removes only owned files, retaining modified user files |
| R078 | P0 | BLOCKED | Guest reboot, normal Cinnamon login and rollback are proven |
| R079 | P1 | GAP | Install works with no internet after dependencies are staged |
| R080 | P1 | GAP | Mint edition and X11/Wayland compatibility matrix is recorded |
| R081 | P1 | GAP | A recovery path exists for missing icons, damaged packs and failed updates |

## CI, regression & independent verification

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R082 | P0 | CI-SCOPED | Source and Python regression suite runs on pull requests |
| R083 | P0 | CI-SCOPED | Qt6 C++ compiles and the visible preview smoke tests in Ubuntu |
| R084 | P0 | CI-SCOPED | The CI supervisor no longer calls all-skipped checks green |
| R085 | P0 | GAP | Required checks are enforced by real branch protection rules |
| R086 | P0 | BLOCKED | Actual Mint GUI acceptance runs automatically on a guest VM |
| R087 | P1 | GAP | Qt C++ has AddressSanitizer and UBSan debug builds |
| R088 | P1 | GAP | Mutation/property-based fuzz tests exercise malformed metadata and rollbacks |
| R089 | P1 | GAP | Visual image comparison measures approved art, not just PNG dimensions |
| R090 | P1 | GAP | Every release has an independent code review and traceable results |

## Packaging, updates, privacy & user trust

| Gate | Priority | Evidence level | Acceptance question |
|---|---|---|---|
| R091 | P0 | GAP | A reproducible distributable package or ISO is built and tested |
| R092 | P0 | GAP | Package signatures and download hashes validate authenticity |
| R093 | P0 | GAP | Updater and rollback are atomic or leave previous mode usable |
| R094 | P0 | GAP | The host cannot silently collect passwords, tokens or personal documents |
| R095 | P1 | GAP | Operational logging is bounded, privacy-preserving and exportable |
| R096 | P1 | GAP | Crash telemetry is user-controlled and disabled by default |
| R097 | P1 | GAP | A clean install/uninstall is tested on an independent Mint VM |
| R098 | P1 | GAP | Third-party pack licenses and trademark/IP provenance are checked |
| R099 | P1 | GAP | Release notes distinguish tested features from future roadmap claims |

## Initial totals and decision discipline

- 99 distinct gates in 11 categories (9 each). Scoped checks: **18**; gaps: **73**; externally blocked: **8**.
- Do **not** compute a product-wide percent-complete score from scoped test passes; every category must be exercised in its actual runtime environment.
- Next actions: finish a genuine Mint acceptance test lab, get a reversible safe app-menu/session installation path, fix icon optical balance using actual compiled Qt evidence, design the real compositor and shared service boundary, and instrument 5-minute PSS/CPU and long soak/switch tests.
- QA gate owner must attach exact SHA, command, environment, screenshot/log artifact and PASS/FAIL/BLOCKED evidence to each completed P0 item before a user-facing release.
- Do not solicit external reviewers unless requested; code review remains open, and the project owner's existing reviewers can inspect these gates directly.
