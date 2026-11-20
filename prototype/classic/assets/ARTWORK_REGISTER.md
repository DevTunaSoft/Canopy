# Canopy Classic artwork register

**Status:** candidate artwork in an unapproved visual rebuild branch; NOT a release icon theme.

| Source | Identity | Authorship | Used for |
| --- | --- | --- | --- |
| `assets/wallpapers/blue-current.svg` | Blue Current | Independently authored Canopy curves/gradients; no Apple wallpaper traced | Static light wallpaper |
| `assets/icons/home.svg` | Canopy Home | Original stylized house | Demo home item |
| `assets/icons/files.svg` | Canopy Files | Original layered blue folder | Dock Files and consistent sample folders |
| `assets/icons/browser.svg` | Canopy Navigator | Original compass construction | Browser concept |
| `assets/icons/photos.svg` | Canopy Gallery | Original chromatic shutter pattern | Photos concept |
| `assets/icons/mail.svg` | Canopy Post | Original stationery envelope construction | Mail concept |
| `assets/icons/calendar.svg` | Canopy Calendar | Original dated paper sheet concept | Calendar concept |
| `assets/icons/settings.svg` | Canopy Settings | Original machined gear | Preferences concept |

These files were authored specifically for Canopy, use gradients and geometric
primitives, and incorporate no source imagery, fonts or SVGs from Apple.
Comparable desktop/interface conventions do not license Apple's protected
logos or images. Do not attach Apple's brand names, app icons, fonts or
screenshots to released assets.

**Distribution:** Before any public installer release, choose the repository's
software and artwork redistribution licenses, confirm provenance, and record
their exact SPDX identifiers here. This register is an authorship record, not
a warranty or a substitute for the release license review.

**Engineering:** Wallpaper and icon assets are stored as static source,
embedded into a Qt resource, decoded by `libqt6svg6` on Ubuntu 24.04, and
checked using `tools/check_art_asset.py`, `tools/check_icon_set.py`,
source regressions and the runtime `Image.Ready` gate. The demo does not
implement actual file browsing, app launching, or system controls.

**Visual acceptance:** All artwork remains subject to owner screenshot review.
Originality, passed CI, and low resource usage do not establish premium finish.
