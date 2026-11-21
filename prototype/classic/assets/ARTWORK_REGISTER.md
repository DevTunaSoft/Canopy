# Canopy Classic artwork register — source-trace experiment

**Status: NOT DESIGN-APPROVED.** See [visual provenance](../../../docs/VISUAL_REFERENCE_PROVENANCE.md).
The screenshot icon set from PR #72 was rejected by the user because it was
presented as supplied artwork when it was an invented reinterpretation.

| Source file | Role | Source / accuracy |
| --- | --- | --- |
| `brand/penguin-launcher.svg` | Menu-bar launcher | Vector trace of recovered `Minimalist White Penguin Silhouette.png` (original PNG SHA-256 recorded in provenance). White silhouette, black cutouts; no new gold/green penguin. |
| `icons/files.svg` | Files | Original candidate; not an extracted Finder icon |
| `icons/browser.svg` | Browser | Original compass candidate; not an extracted Safari icon |
| `icons/settings.svg` | Settings | Original gear candidate; not an extracted Apple Settings icon |
| `icons/photos.svg` | Photos | Original green landscape candidate replacing the rejected flower/shutter; not an Apple Photos icon |
| `icons/terminal.svg` | Terminal | Original dark terminal candidate |
| `icons/trash.svg` | Trash | Original bin candidate |
| `wallpapers/blue-current.svg` | Wallpaper | Original static blue artwork candidate; NOT the forest imagery in the recovered board |

**Rejected prior substitute:** `icons/canopy.svg` from PR #72 was an
invented tree-and-colored-penguin app icon. It has been removed from the
current preview branch. Restore only if explicitly selected with a verified
source and visual review.

The six dock icon categories (folder, compass, settings gear, landscape,
terminal, trash) are documented in a previously generated project moodboard;
the exact artwork within that board is **not proven to be a user-approved
redistributable icon set**. Retain the engineering implementation but make no
claim of image identity or final quality.

Release gate: establish licensing, source provenance, screenshot acceptance,
keyboard and high-DPI behavior and Linux Mint installation results before any
candidate may be treated as production artwork.
