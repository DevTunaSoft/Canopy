# Canopy premium original icon system — selectable asset program

This is an original design workstream, not an export of any Apple icon artwork. The SVG samples in `prototype/classic/assets/icons/` are self-contained first-pass design candidates and **are not yet integrated into the actual Qt shell**. User approval and screenshot acceptance are required before integration.

## Independent user choices

Choose *per icon*, not by an all-or-nothing theme. Each app can select its own candidate without changing other apps:
- **A — Luminous:** vivid chromatic gradient, glass-like upper highlight, greater dimensional depth
- **B — Satin:** restrained matte/satin gradient, understated edge light
- **C — Sculpted:** rich dimensional central symbol with a quieter background

A, B and C designate future variations, not three assets already shipped. The current four proof-of-concept sources are not approved product assets; three were redesigned after an Apple-lookalike review. No claimed legal clearance is implied.

## Initial vector candidates

| App | Source | Differentiation |
| --- | --- | --- |
| Browser | `browser.svg` | Original flowing exploration path, without a circular dial or needle |
| Files | `files.svg` | Offset tapered archive flap and distinct teal-indigo wave seam |
| Mail | `mail.svg` | Asymmetric flying-paper message mark on a plum canvas instead of a white envelope on blue |
| Terminal | `terminal.svg` | Dark instrument card with luminous two-color prompt |

The original Tux mascot is **separate** from these original app icons. Do not redesign Tux as another penguin or suggest these icons make Tux exclusive. Select an appropriately licensed, attributable original Tux artwork derivative for menu/dock and preserve Larry Ewing credit.

## Full icon family roadmap
Launcher / Tux, Browser, Mail, Calendar, Files, Photos, Videos, Music, Terminal, Settings, Trash, Help, Software, System Monitor, Contacts, Maps, Reminders, Calculator. Also include folders and application-specific document symbols.

## Acceptance & resource constraints

- SVG source checked into Git, no hotlinked raster resources, fonts, animations, network requests or embedded scripts.
- Retain 128×128 reference viewBox; render prepared 64/128/256px assets as appropriate, cache after first use, and measure actual Qt and Linux Mint footprint.
- Tests check SVG syntax/security, and Qt runtime screenshots must show the *actual* selected icon before promotion.
- Icon silhouette must remain identifiable at 24px, 48px, 64px; prove consistent margins and optical baseline.
- Avoid Apple's exact stylized symbols, distinctive icon arrangements, trademarks, or proprietary artwork even where the broad interaction pattern is familiar.
- Keep current dock Canvas fallback until a separately tested Qt SVG rendering path is available.
- License inventory and per-source provenance required before commercial release.

## Selection workflow

1. Show labeled A/B/C renders of each candidate in consistent tiles at 48px and 128px.
2. User selects a winner *for each application* and can combine across styles.
3. Store selections in a declarative asset manifest to support variants without branching app logic.
4. Wire chosen assets into dock/launcher/file browser, verify screenshots and keyboard/accessibility.
5. Keep draft until approved. Current samples represent a proof-of-concept batch, not a production icon pack.

## IP and similarity hold — 2026-11-19

The user identified too-close resemblance in the concept sheets. Treat *every* new icon as **unapproved** until a separate visual similarity review and legal clearance appropriate to release. Apple trademark/trade dress guidance: https://www.apple.com/legal/intellectual-property/guidelinesfor3rdparties.html . Copyright Office background: https://www.copyright.gov/circs/circ33.pdf . These are research references, **not** legal opinions or guarantees.

- **Replace / avoid:** circular compass resembling Safari; white envelope on blue tile resembling Apple Mail; Apple's multicolored Photos flower; red-header Calendar tile; metallic gear in Apple's exact look; any closely matching Apple symbol, coloring, detailing or arrangement.
- **Keep independent:** generic command-line prompt, but with Canopy typography and lighting; abstract folder/file concept with independently designed geometry; original exploratory path and asymmetric folded-message symbol.
- **No silent integration:** no candidate may become a default Qt shell asset, screenshot marketing sample, or release deliverable without explicit approval and documented origin/review.
- **Mockup disclaimer:** earlier polished concept images contain Apple-adjacent designs and must remain *reference-only*, not a source from which to crop icons or vector-trace them.
- **Tux licensing separate:** authenticate the source illustration and attribution before distribution; do not confuse permission to use Tux with rights to trademark him exclusively.
- **Similarity review process:** compare side-by-side with current Apple, other third-party icons, and Canopy candidates at 32/64/128px; check distinctive shapes, layout, palette, proportion and overall commercial impression; reject close variants; commission legal review before commercial launch.
