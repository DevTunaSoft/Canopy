# LacOS immutable architecture and application compatibility
Owner requirements, 2026-11-27. DESIGN / NOT IMPLEMENTED. Supplements PLASMA6_PIVOT.md. Finish current assignments; independent lightweight research only until native Classic is on track. No change to protected artwork, branch rules, workforce cap or release approval.

## Core and security
Production LacOS must run with a genuinely read-only versioned OS deployment (including /usr and merged /bin, /sbin, /lib); ordinary package operations must not mutate the booted core. Keep /home, /var and necessary /etc configuration state separate and persistent; protect boot artifacts and privileged configuration. Validate mount/overlay semantics. No chmod-only immutability or routine writable remount. Evaluate verified boot, signed images, least privilege, mandatory access controls, encryption option, signed repositories, recovery, key rotation and rollback protection. Read-only is not a guarantee against root/kernel compromise or user-data theft.

## Updates and base selection
Use supported upstream kernel, driver, library, security and desktop packages in reproducible image builds. Maintain automated rebuild/test/sign/publish pipeline, SBOM, provenance and CVE triage; separate staged/stable channels and owner-approved release policy. Verify inactive deployments before atomic activation; retain known-good bootable revision and recover without losing personal data. Test power loss, disk full, failed boot, bad signatures, incompatible state migration, Secure Boot, GPU drivers and major upgrades. OS rollback does not imply rollback of user data or container/Flatpak state. Provide Mint-inspired graphical update/recovery experience with independent core, app and container status. Verify exact component support, including Plasma; Ubuntu standard support is not blanket coverage of all repositories. LacOS owns image delivery even when upstream maintains packages.

Kubuntu LTS is a mutable reference guest only. Add KDE neon as a latest-upstream compatibility lane (not a presumed stable base); evaluate Fedora Kinoite, openSUSE Kalpa, Vanilla OS ABRoot/APX, blendOS, and Ubuntu LTS image-based options, including Ubuntu Core's snap-centric tradeoffs and bootc applicability. Compare maturity, supported update lifecycle, secure boot, hardware, image rollback, storage, RAM and maintenance cost. Do not mix repositories or lock the final base/backend before proof. If upstream design questions remain, consult KDE developer documentation and prepare focused questions for KDE Discuss/Matrix; no public outreach without separate authorization.

## Application installation options
- Flatpak: default graphical application option, prefer per-user installs and portals, expose permissions and origin.
- APT/dpkg: Ubuntu/Debian mutable application environments using rootless containers; .deb support where compatible. If a Debian-family base is selected, image-build APT is allowed, not live host APT mutation.
- Pacman: Arch mutable rootless environments, full supported upgrades, no partial upgrades, no Arch packages or repositories in host root. AUR optional explicit opt-in, review untrusted build recipes.
- Podman: daemonless rootless OCI engine, on-demand environments, no privileged defaults, unrestricted host mounts or socket access. Evaluate Distrobox/APX for trusted convenience workflows; Distrobox shares host resources and is not a security sandbox. Separate restricted environments for untrusted software; custom HOME alone is not isolation.
- Host-only drivers, kernel modules and system services: curated new signed deployment through selected backend, not arbitrary container export into /usr.
Provide a unified graphical app center and explicit source-aware CLI; reuse Discover/Flatpak and mature container tooling where practical. Distinguish app identities by source, integrate launchers/icons/file associations safely, show install/update/uninstall state, disk usage, permissions and supported architectures. Do not silently substitute sources, execute arbitrary scripts on host, promise universal GUI compatibility, or merge package databases. Test ordinary user install/update/remove for each supported method, GUI launch, isolation, no host mutation, interrupted operations, storage cleanup and low-end performance. No always-running container service merely to offer package options.

## Canopy Modern — Zorin OS inspiration
Research Zorin Appearance, Windows-familiar application menu/search, taskbar layouts, window snapping, tray, quick settings, onboarding, app alternatives and accessibility. Retain native Plasma/KWin and one shared Canopy host; do not port a second GNOME desktop. Create original Canopy artwork, branding and implementations; respect upstream licenses and proprietary assets; do not imply affiliation. Owner-approved Classic unchanged. Produce real compiled native Modern screenshots and functional keyboard/mouse/HiDPI evidence. Shell Pack switcher must preserve apps and recover prior presentation; no promise before tests.

## Gate sequencing
Native Classic remains primary deliverable; independent research can proceed under existing cap. Record exact sources, licenses, test environment and SHA. Before LacOS release, demonstrate read-only core during normal app installation, verified atomic updates and rollback, all four app options, upstream support lifecycle, real hardware and VM acceptance, security/fault injection, resource budgets, accessibility, original visual acceptance. No claims of implementation or performance wins without evidence. Public releases require owner approval.

## Research starting points
- https://neon.kde.org/faq
- https://develop.kde.org/docs/getting-started/building/help-developers/
- https://develop.kde.org/docs/getting-started/building/containers-distrobox/
- https://fedoraproject.org/atomic-desktops/kinoite/
- https://kalpadesktop.org/
- https://vanillaos.org/
- https://blendos.co/
- https://zorin.com/os/
- https://docs.podman.io/
- https://docs.flatpak.org/
