# Review the actual Canopy Classic Qt screenshots offline

**Status:** Evidence viewer, not a Qt screenshot generator, production build,
Linux Mint acceptance test, or visual approval. The approved artwork stays
outside the public repository.

A reviewer can compare two independent runs of the *same compiled Qt binary*
using the existing Mint Classic Qt smoke runner. Capture a baseline
without the --icon-framing-review option and a candidate with it, each under a NEW
private output directory. Both reports must say PASS and contain original
screenshots at 1920x1080, 1200x750 and 760x500.

On a machine with both reports:

    python3 -m tools.classic_visual_review \
      --baseline-dir /absolute/private/baseline \
      --candidate-dir /absolute/private/candidate \
      --output-dir /absolute/private/visual-review

Open the generated visual-review/index.html in a local browser. Both columns
are actual input PNGs, **copied byte-for-byte**. No CSS is used to move any icon
relative to its own screenshot; the page merely scales the full screenshots for
viewing. Click each image to see the original pixel dimensions.

Safety behavior:

- Refuses non-PASS or inconsistent reports, wrong ordering/resolutions,
  mismatched source claims or measured binary SHA-256, missing/corrupted PNGs,
  unexpected file names and links at reviewed input paths.
- Refuses to overwrite any existing output directory, creates a private
  directory with 0700 permissions, and writes private 0600 files.
- Contains no scripts, remote assets, web requests, logging or telemetry.
- Does not republish the original selected icons or landscape wallpaper to
  GitHub. Do **not** commit generated evidence or expose it on a public site.
- The generated review.json lists only hashes and evidence status; it does not
  contain local source file paths, stdout/stderr or environment variables.
- Test inputs are self-reported: even a PASS report and matching hashes cannot
  independently prove that screenshots came from a real Qt process, that the
  measured binary was built from the claimed source SHA, or that Mint accepted
  a complete desktop session. Review original provenance separately.

This tool never sets visual_owner_approval to PASS. Side-by-side presentation
helps a human determine whether the original icons, alpine wallpaper, dock
proportions and optical spacing actually look premium and consistent. The owner
must explicitly approve the appearance before any visual PR can be merged.

Run synthetic negative-control tests with:

    python3 -m unittest tests.test_classic_visual_review -v

These tests use generated test PNGs rather than approved artwork or real Qt
screenshots. Real Linux Mint guest execution and visual acceptance remain
separate acceptance gates.
