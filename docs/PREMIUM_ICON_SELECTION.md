# Canopy premium original icon system — selectable asset program

This is an original design workstream, not an export of any Apple icon artwork. The SVG samples in `prototype/classic/assets/icons/` are self-contained first-pass design candidates and **are not yet integrated into the actual Qt shell**. User approval and screenshot acceptance are required before integration.

## Independent user choices

Choose *per icon*, not by an all-or-nothing theme. Each app can select its own candidate without changing other apps:
- **A — Luminous:** vivid chromatic gradient, glass-like upper highlight, greater dimensional depth
- **B — Satin:** restrained matte/satin gradient, understated edge light
- **C — Sculpted:** rich dimensional central symbol with a quieter background

A, B and C designate future variations, not three assets already shipped. The current four proof-of-concept sources are in the Luminous direction.

## Initial vector candidates

| App | Source | Differentiation |
| --- | --- | --- |
| Browser | `browser.svg` | Original asymmetric navigation pointer in a circular instrument, not Safari's compass |
| Files | `files.svg` | Tabbed folder with a wavelike seam, designed for Canopy |
| Mail | `mail.svg` | Soft pearlescent envelope folded against a turquoise-blue field |
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
