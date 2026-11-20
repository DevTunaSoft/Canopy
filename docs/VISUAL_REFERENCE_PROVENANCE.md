# Canopy Classic — reference provenance and locked corrections

**Visual status:** VISUAL_REVIEW_PENDING. This file records evidence from archived
images, not an implied user approval of every component in a generated board.

## Confirmed user instructions
- Default Classic layout should feel extremely familiar to macOS, while
  avoiding copied Apple artwork or trademarks.
- Upper-left launcher is a **complete white Tux-inspired penguin silhouette**
  like a simple white logo on a black/dark background. No yellow feet,
  gold beak, green tree, gradient body or substitute penguin character.
- Resource-efficient but premium and meticulously aligned, not "lightweight
  mode" cartoon art. Real Qt screenshots must be visually reviewed.
- Official product tagline for copy only is:
  **The Familiar Feel. The Freedom of Linux.**

## Files actually recovered

| Archived visual file | Identifying detail | Authority |
| --- | --- | --- |
| `Minimalist White Penguin Silhouette.png` | 1254×1254 white silhouette with black eyes, beak and black background; source SHA-256 `6bc6fbf22a8da5f20af4b6f35ec6647dbb80923d96480d831190d6159282724f` | Matches the explicit white-on-black launcher instruction. Source generated earlier in the Canopy design conversation. |
| `Canopy Desktop Shell Brand Moodboard.png` | Forest green `#1B5E3B`, charcoal `#1F2326`, ivory `#F7F5EB`, soft gold `#D8B87A`. Desktop bar and a **six-icon** example dock: folder, compass, settings gear, landscape gallery, terminal, trash. | A recovered concept reference; **not proof these are individually approved master assets**. |
| `Canopy Tree Logo on Ivory.png` | Green tree silhouette, charcoal trunk, no penguin inside the icon. | A separate concept mark, **not** the top-left launcher reference. |
| `Canopy Desktop Shell Promotional Wallpaper.png` | Different glossy green swoosh + penguin concept, includes sample dock icons styled after commercial apps. | Earlier generated promotional visual, not licensed application icon source and **not** the definitive desktop artwork. |

The image files above were retrieved from existing Canopy Library/Project context,
not regenerated or inferred from source QML. If they are later added to the
repository, preserve original bytes and hashes; no one should claim an editable
SVG is an original master unless it is. Sources may have been generated during
prior ChatGPT design work and must not be represented as user-uploaded files
without provenance.

## This isolated implementation

- `prototype/classic/assets/brand/penguin-launcher.svg` is a vector
  **trace** of the recovered white silhouette PNG: 128×128 coordinates,
  original contour + three negative-space facial cutouts.
  This is not a byte-identical image. Only resizing and threshold/outline
  tracing were applied; the image was **not creatively redrawn**.
- The top menu bar uses charcoal and ivory for visibility. The launcher is
  separate from dock application icons.
- The preview dock contains six **categories**, in the moodboard's order:
  Files / Browser / Settings / Photos / Terminal / Trash. The invented Canopy
  tree-and-penguin app icon is explicitly retired from this preview.
- Photos is an independently authored landscape illustration rather than the
  previous unrelated flower/shutter candidate. All six dock pictures are
  still **original candidate artwork**, not exact icons taken from the board.

## Hard no-hallucination release gates

1. Never say "exact icons you sent" based only on the recovered moodboard.
   Only the launcher silhouette has a direct shape reference in the branch.
2. No Apple-owned Finder, Safari, Photos, Settings or Trash graphics may be
   extracted from the moodboard and redistributed. Use original equivalents.
3. Do not claim this screen is the finished shell; it remains a standalone
   Qt test scene with synthetic folders and no real desktop session.
4. Validate runtime: SVG launcher loaded, six dock images loaded, correct
   order/layout, 760×500 / 1200×750 / 1920×1080 screen captures and idle data.
5. Human approval of actual screenshots, Linux Mint guest validation, native
   status/menu/file integration, and high-DPI review are still outstanding.
6. If a later message provides an exact master icon package or explicit
   approved reference, replace these candidates with that evidence **without
   guessing**, update this file, and only then describe the result as matched.
