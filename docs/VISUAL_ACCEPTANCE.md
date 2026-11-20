# Canopy Classic visual and performance acceptance

Status: engineering specification; **not verified on Linux Mint**.

**Mandatory visual brief:** [PREMIUM_DESIGN_DIRECTION.md](PREMIUM_DESIGN_DIRECTION.md).
The current standalone preview is **not** an approved high-quality skin. The new
original lakeside wallpaper, seven-icon dock, and sample Files window are a first
visual refinement, not proof that the result is premium or that demo controls work.

## Evidence-led review, November 20, 2026

The first landscape-and-seven-icon screenshot build at commit `5102356`
passed automated Qt tests (GitHub Actions run 44769825430), producing actual
1200×750 and 760×500 PNGs. Inspection identified **visual shortcomings**:
the Files window had excessive blank space, flat sample folders, and insufficient
navigation/toolbar detail. The initial image must not be treated as approved.

Subsequent draft changes introduce a compact-aware toolbar, reusable folder
artwork, keyboard-accessible sample navigation, search filtering, and sample
selection. These actions only change local demo data; they are **not** operating
system or filesystem features. All later screenshots require a fresh visual
review on the exact post-change commit. Source-level tests cannot certify this.

## Design intent

Canopy Classic must look deliberately composed and premium at both compact and standard
sizes, rather than mimic proprietary macOS art or rely on resource-heavy blur.
The top bar, launcher, and dock are the first components to polish. Keep all artwork
original and license-audited. The shell remains a standalone Qt technology spike
until actual session ownership, app launching, accessibility, and window management work.

## Visual review matrix

Review captured evidence at 760x500 and 1200x750 first, then a real Linux Mint session
at 1920x1080 and a high-DPI configuration. A successful PNG capture is **not** proof
of attractive or correct rendering. The runtime geometry tests additionally verify
that the wallpaper covers the viewport and all seven dock tiles are instantiated;
these checks cannot judge icon craft, layout aesthetics, contrast or composition.

For each image, a reviewer must confirm:

- No clipped, overlapping, illegible, or unexpectedly hidden interface elements.
- Dock is horizontally centered, keeps consistent padding, and does not collide with text.
- Top-bar launcher, labels, and date have legible contrast and deliberate alignment.
- Iconography is coherent, original, visually balanced, and accessible.
- Color, hierarchy, spacing, edge treatment, and surface depth are restrained and consistent.
- Keyboard focus and hover cues are visible; usability is not hover-dependent.
- Dark theme remains readable; no visible color banding or broken scaling.

Fail the visual gate for meaningful defects, placeholder-grade artwork, toy-like
four-button dock layouts, or the absence of a representative interactive
application window. Attach annotated screenshots.
Do not label automatic screenshot verification a visual review.

## Performance and resource budget

The original Canvas wallpaper allocates an image backing store and must be checked
at native 1080p and high DPI (including software-rendering fallback). Collect **actual**
guest measurements before choosing numeric release thresholds:
cold/warm startup, 5-minute idle CPU, PSS from /proc/PID/smaps_rollup, and GPU
behavior on software and accelerated backends. Preserve machine, compositor,
Qt, resolution, scaling, and driver details beside each sample.

Profiles: Auto, Ultra Lightweight, Lightweight, Balanced, Enhanced, and Premium.
Profiles are **planned**, not implemented. Their implementation must share
one theme and core services; do not fork the shell or run duplicated daemons.
Subtle depth must degrade gracefully without becoming visually cheap.

## Automated gate versus human acceptance

GitHub Actions currently checks foundation tests, builds Qt, launches the
window under Xvfb, validates screenshot integrity and dimensions, and records
an informational five-second CPU/PSS sample in the UI evidence artifact.
That short software-rendered measurement is not a production performance
budget or a substitute for five-minute idle tests on Linux Mint.
It does not verify rendering aesthetics, real session behavior, or Mint
performance. CI failures block promotion; screenshots must be reviewed
before any visual-completion claim. Never silently replace failed
acceptance evidence with a placeholder or stale screenshot.

## Release stages

1. Qt source, build, startup, and screenshot CI pass.
2. Screenshots reviewed and defects triaged.
3. Dedicated Linux Mint VM tested; evidence recorded per docs/MINT_VM_ACCEPTANCE.md.
4. Performance baselines captured and compared across changes.
5. Only then consider a candidate desktop-session milestone.
