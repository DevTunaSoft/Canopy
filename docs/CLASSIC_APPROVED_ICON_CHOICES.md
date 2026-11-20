# Canopy Classic approved icon selections (2026-11-20)

Eight **visual concepts** were explicitly selected by the project owner from the original eight-option artwork comparison, not from the draft SVGs currently in the repository.

| Application | Approved original option | Recognizable motif |
| --- | ---: | --- |
| Browser | 3 | Tux + orbiting globe |
| Mail | 5 | @ envelope + golden orbital trail |
| Files | 2 | Tux + yellow documents folder |
| Calendar | 3 | Stacked calendar pages + Tux |
| Photos | 2 | Overlapping mountain landscape photos |
| Music | 3 | Tux + headphones + equalizer |
| Terminal | 4 | Terminal prompt + Tux |
| Settings | 8 | Gear + Tux |

The source of truth for the exact option numbers is `prototype/classic/assets/icons/classic-approved-selections.json`.
Run `python -m unittest tests.test_classic_approved_icons -v` to check the manifest contract. Existing icon source checks remain separate.

## Production integration gate

- This is approval of the **selection**, not a licensing review, production asset approval, or Qt implementation.
- Do **not** substitute `browser.svg`, `mail.svg`, `files.svg`, or `terminal.svg` from the earlier prototype: those are unrelated first-pass sources.
- The original concept artwork is currently maintained in the visual comparison materials; high-resolution independently editable source files have **not** been added to this repository. `production_asset: null` is intentional.
- Do not crop and ship a low-resolution thumbnail as a final icon. Reconstruct each approved design faithfully, obtain appropriately licensed Tux source artwork and credit Larry Ewing/GIMP, record per-asset provenance and IP review, then ask for visual approval where faithfully matching the chosen composition requires changes.
- Once source artwork is checked in, update the manifest with audited asset paths, wire into the Qt dock **and** launcher, capture actual Qt screenshots at 24/48/64/128px and standard/compact/high-DPI sizes, validate transparency and accessibility, and keep a no-asset graceful fallback.
- Keep the visual treatment premium and static/cached with no additional polling, background daemons or continuous blur. Measure resource usage on the Linux Mint VM before promotion.
- Existing draft PRs must remain draft until acceptance and CI evidence are confirmed. Do not merge this selection-record milestone as if it were finished artwork.
